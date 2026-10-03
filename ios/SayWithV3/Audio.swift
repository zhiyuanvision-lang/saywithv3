import AVFoundation
import Observation

@MainActor @Observable
final class AudioController: NSObject, AVAudioPlayerDelegate, AVAudioRecorderDelegate {
    var recording=false
    var playing=false
    var paused=false
    var playingID:String?
    var interruptionMessage:String?
    var lastRecording:Data?
    var duration:TimeInterval=0
    private var recorder:AVAudioRecorder?
    private var player:AVAudioPlayer?
    private var file:URL?
    private var observer:NSObjectProtocol?
    private var timer:Task<Void,Never>?
    override init() {
        super.init()
        observer=NotificationCenter.default.addObserver(forName:AVAudioSession.interruptionNotification,object:nil,queue:.main) { [weak self] notification in
            let began=(notification.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt)==AVAudioSession.InterruptionType.began.rawValue
            if began {Task { @MainActor in self?.discard();self?.interruptionMessage="录音被系统中断，请重新录制。" }}
        }
    }
    func start() async throws {
        guard await AVAudioApplication.requestRecordPermission() else {throw APIError.server("请在系统设置中允许麦克风访问。")}
        stopPlayback();lastRecording=nil;interruptionMessage=nil;duration=0
        let session=AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord,mode:.default,options:[.defaultToSpeaker,.allowBluetoothHFP]);try session.setActive(true)
        let url=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString+".wav")
        let new=try AVAudioRecorder(url:url,settings:[AVFormatIDKey:kAudioFormatLinearPCM,AVSampleRateKey:16000,
            AVNumberOfChannelsKey:1,AVLinearPCMBitDepthKey:16,AVLinearPCMIsFloatKey:false,AVLinearPCMIsBigEndianKey:false])
        new.delegate=self
        guard new.record(forDuration:90) else {throw APIError.server("无法开始录音。")}
        recorder=new;file=url;recording=true
        timer=Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for:.milliseconds(200))
                guard let self,self.recording else {return}
                self.duration=self.recorder?.currentTime ?? 0
            }
        }
    }
    func stop() throws -> Data {
        recorder?.stop();recording=false;timer?.cancel()
        guard let file else {throw APIError.server("没有录音文件。")}
        let data=try Data(contentsOf:file);lastRecording=data
        try? FileManager.default.removeItem(at:file);self.file=nil;recorder=nil
        try? AVAudioSession.sharedInstance().setActive(false,options:.notifyOthersOnDeactivation)
        return data
    }
    func stopPlayback() {player?.stop();player=nil;playing=false;paused=false;playingID=nil}
    func pausePlayback() {player?.pause();playing=false;paused=true}
    func resumePlayback() throws {guard player?.play()==true else {throw APIError.server("声音暂时无法播放，请重试。")};playing=true;paused=false}
    func discard() {
        recorder?.stop();recording=false;recorder=nil;timer?.cancel();stopPlayback()
        if let file {try? FileManager.default.removeItem(at:file)}
        file=nil;lastRecording=nil
        try? AVAudioSession.sharedInstance().setActive(false,options:.notifyOthersOnDeactivation)
    }
    func play(_ data:Data,id:String="own",rate:Float=1) throws {
        guard !recording else {return}
        stopPlayback()
        let session=AVAudioSession.sharedInstance()
        try session.setCategory(.playback,mode:.spokenAudio);try session.setActive(true)
        let new=try AVAudioPlayer(data:data);new.delegate=self;new.enableRate=true;new.rate=rate
        guard new.play() else {throw APIError.server("声音暂时无法播放，请重试。")}
        player=new;playing=true;playingID=id
    }
    func playAndWait(_ data:Data,id:String) async throws {
        try play(data,id:id)
        while playing && playingID==id {
            try await Task.sleep(for:.milliseconds(80))
        }
    }
    nonisolated func audioPlayerDidFinishPlaying(_ player:AVAudioPlayer,successfully flag:Bool) {
        let identity=ObjectIdentifier(player)
        Task { @MainActor [weak self] in
            guard let self,let active=self.player,ObjectIdentifier(active)==identity else {return}
            self.playing=false;self.paused=false;self.playingID=nil
        }
    }
    nonisolated func audioRecorderDidFinishRecording(_ recorder:AVAudioRecorder,successfully flag:Bool) {
        Task { @MainActor [weak self] in
            guard let self,self.recording else {return}
            self.recording=false;self.timer?.cancel()
            if let file=self.file {self.lastRecording=try? Data(contentsOf:file);try? FileManager.default.removeItem(at:file);self.file=nil}
            self.recorder=nil
            self.interruptionMessage="录音已达到时长上限，可回听后发送，或重新录制。"
        }
    }
}
