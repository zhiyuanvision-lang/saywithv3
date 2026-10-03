"""Reuse SayWith's verified identities; issue separate short-lived learning sessions.

Only hashes of credentials are persisted here. SMS, Apple verification, WeChat
code exchange, and rotating refresh tokens remain with the existing auth service.
"""
import hashlib
import secrets
import time

import httpx
from fastapi import HTTPException
from sqlalchemy import delete, insert, select, update, text

from .contracts import LearnerProfile
from .store import uid


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


class Accounts:
    def __init__(self, settings, store):
        self.settings = settings
        self.store = store
        self.client = httpx.AsyncClient(timeout=15, follow_redirects=False)

    async def close(self):
        await self.client.aclose()

    async def upstream(self, path, body=None, token=None, caller=None):
        headers = {'Authorization': 'Bearer ' + token} if token else {}
        # Forward only the ASGI-resolved caller to a configured loopback service.
        # Public nginx overwrites XFF, so it should not be forwarded there.
        if caller and httpx.URL(self.settings.identity_api_base).host in ('localhost', '127.0.0.1'):
            headers['X-Forwarded-For'] = caller
        try:
            response = await self.client.request(
                'POST' if body is not None else 'GET',
                self.settings.identity_api_base + '/v1/auth/' + path,
                json=body, headers=headers,
            )
        except httpx.HTTPError:
            raise HTTPException(503, '登录服务暂时不可用，请稍后重试') from None
        if response.status_code >= 400:
            status = response.status_code if response.status_code in (400, 401, 403, 429) else 503
            detail = {400: '手机号、验证码或授权凭证无效', 401: '登录已失效，请重新登录',
                      403: '当前登录方式不可用', 429: '操作过于频繁，请稍后重试',
                      503: '登录服务暂时不可用，请稍后重试'}[status]
            if status == 401 and path == 'sms/login':
                detail = '验证码错误或已过期，请重新获取验证码'
            elif status == 401 and path in ('apple', 'wechat'):
                detail = '授权凭证无效，请重新授权登录'
            raise HTTPException(status, detail)
        try:
            return response.json() if response.content else {}
        except ValueError:
            raise HTTPException(503, '登录服务返回异常，请稍后重试') from None

    def anonymous_owner(self, token, conn):
        if not token:
            return None
        row = conn.execute(select(self.store.users.c.id).where(
            self.store.users.c.token_hash == token_hash(token))).first()
        if not row:
            return None
        bound = conn.execute(select(self.store.identities.c.owner).where(
            self.store.identities.c.owner == row.id)).first()
        return None if bound else row.id

    def owner(self, token):
        with self.store.engine.connect() as c:
            row = c.execute(select(self.store.auth_sessions.c.owner).where(
                self.store.auth_sessions.c.access_hash == token_hash(token),
                self.store.auth_sessions.c.expires_at > time.time())).first()
            if row:
                return row.owner
            # Existing installations retain their anonymous data until first login.
            anonymous = self.anonymous_owner(token, c)
            if anonymous:
                return anonymous
        raise HTTPException(401, '登录已失效，请重新登录')

    async def login(self, path, body, legacy_token=None, caller=None, previous=None):
        remote = await self.upstream(path, body, caller=caller)
        access = remote.get('access_token')
        refresh = remote.get('refresh_token')
        if not access or not refresh:
            raise HTTPException(503, '登录服务未返回完整凭据')
        # Trust only the authenticated /me result, never client-supplied user IDs.
        identity = await self.upstream('me', token=access)
        external = identity.get('user_id')
        if not isinstance(external, str) or not external or len(external) > 200:
            raise HTTPException(503, '登录身份无效')
        local_access = secrets.token_urlsafe(32)
        expires = min(max(int(remote.get('expires_in') or 7200), 1), 7200)
        adopted = False
        with self.store.transaction() as c:
            if self.store.engine.dialect.name == 'sqlite':
                c.exec_driver_sql('BEGIN IMMEDIATE')
            if self.store.engine.dialect.name == 'postgresql':
                c.execute(text('SELECT pg_advisory_xact_lock(:key)'),
                          {'key': int(token_hash(external)[:15], 16)})
            mapping = c.execute(select(self.store.identities).where(
                self.store.identities.c.external_id == external)).mappings().first()
            if previous and (not mapping or mapping['owner'] != previous['owner']):
                raise HTTPException(401, '刷新登录身份不一致，请重新登录')
            if mapping:
                owner = mapping['owner']
            else:
                # A token is required to adopt anonymous records. It cannot be used
                # to claim a second identity or merge into an established account.
                if legacy_token:
                    c.execute(update(self.store.users).where(
                        self.store.users.c.token_hash == token_hash(legacy_token)).values(
                            created_at=self.store.users.c.created_at))
                owner = self.anonymous_owner(legacy_token, c) or uid()
                exists = c.execute(select(self.store.users.c.id).where(self.store.users.c.id == owner)).first()
                if not exists:
                    c.execute(insert(self.store.users).values(id=owner,
                        token_hash=token_hash(secrets.token_urlsafe(32)), created_at=time.time()))
                    profile = LearnerProfile(user_id=owner, preferences={
                        'context': '校园与日常生活', 'reference_stage': 'A2', 'interests': []}).model_dump()
                    self.store.put('LearnerProfile', owner, owner, profile, conn=c)
                else:
                    adopted = True
                    # Revoke the old anonymous bearer once its records are bound.
                    c.execute(update(self.store.users).where(self.store.users.c.id == owner).values(
                        token_hash=token_hash(secrets.token_urlsafe(32))))
                c.execute(insert(self.store.identities).values(external_id=external, owner=owner))
            if previous:
                result = c.execute(delete(self.store.auth_sessions).where(
                    self.store.auth_sessions.c.refresh_hash == previous['refresh_hash']))
                if result.rowcount != 1:
                    raise HTTPException(401, '登录已失效，请重新登录')
            c.execute(insert(self.store.auth_sessions).values(access_hash=token_hash(local_access),
                refresh_hash=token_hash(refresh), owner=owner, expires_at=time.time() + expires))
        return {'user_id': owner, 'display_name': identity.get('display_name') or '学习者',
                'phone': identity.get('phone') or '', 'access_token': local_access,
                'refresh_token': refresh, 'expires_in': expires, 'adopted_anonymous': adopted}

    async def refresh(self, refresh, caller=None):
        with self.store.engine.connect() as c:
            previous = c.execute(select(self.store.auth_sessions).where(
                self.store.auth_sessions.c.refresh_hash == token_hash(refresh))).mappings().first()
        if not previous:
            raise HTTPException(401, '登录已失效，请重新登录')
        return await self.login('token/refresh', {'refresh_token': refresh}, caller=caller, previous=previous)

    async def logout(self, refresh):
        with self.store.transaction() as c:
            c.execute(delete(self.store.auth_sessions).where(
                self.store.auth_sessions.c.refresh_hash == token_hash(refresh)))
        # Local revocation is authoritative even during an identity-service outage.
        try:
            await self.upstream('logout', {'refresh_token': refresh})
        except HTTPException:
            pass
        return {'status': 'signed_out'}
