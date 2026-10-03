import AVFoundation
import Observation

@MainActor @Observable
final class AudioController {
    var recording = false
    var interruptionMessage: String?
    private var recorder: AVAudioRecorder?
    private var player: AVAudioPlayer?
    private var file: URL?
    private var observer: NSObjectProtocol?
    init() {
        observer=NotificationCenter.default.addObserver(forName:AVAudioSession.interruptionNotification,object:nil,queue:.main) { [weak self] notification in
            let began=(notification.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt) == AVAudioSession.InterruptionType.began.rawValue
            if began {Task { @MainActor in
                self?.discard();self?.player?.pause();self?.interruptionMessage="录音被系统中断，请重新录制。"
            }}
        }
    }
    func start() async throws {
        guard await AVAudioApplication.requestRecordPermission() else {throw APIError.server("请在系统设置中允许麦克风访问。")}
        player?.stop();interruptionMessage=nil
        let session=AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord,mode:.default,options:[.defaultToSpeaker,.allowBluetoothHFP])
        try session.setActive(true)
        let url=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString+".wav")
        let recorder=try AVAudioRecorder(url:url,settings:[AVFormatIDKey:kAudioFormatLinearPCM,
            AVSampleRateKey:16000,AVNumberOfChannelsKey:1,AVLinearPCMBitDepthKey:16,
            AVLinearPCMIsFloatKey:false,AVLinearPCMIsBigEndianKey:false])
        guard recorder.record(forDuration:90) else {throw APIError.server("无法开始录音。")}
        self.recorder=recorder;file=url;recording=true
    }
    func stop() throws -> Data {
        recorder?.stop();recording=false
        guard let file else {throw APIError.server("没有录音文件。")}
        defer {try? FileManager.default.removeItem(at:file);self.file=nil;recorder=nil}
        let data=try Data(contentsOf:file)
        try? AVAudioSession.sharedInstance().setActive(false,options:.notifyOthersOnDeactivation)
        return data
    }
    func discard() {
        recorder?.stop();recording=false;recorder=nil
        if let file {try? FileManager.default.removeItem(at:file)}
        file=nil
        try? AVAudioSession.sharedInstance().setActive(false,options:.notifyOthersOnDeactivation)
    }
    func play(_ data: Data) throws {
        guard !recording else {return}
        let session=AVAudioSession.sharedInstance()
        try session.setCategory(.playback,mode:.spokenAudio);try session.setActive(true)
        player=try AVAudioPlayer(data:data);player?.play()
    }
}
