import AVFoundation
import Foundation

/// Captures audio via AVAudioEngine, converts Float32 → Int16, writes a
/// 16kHz mono PCM WAV to the app cache directory, then calls
/// ``VakyaBridge/wavReady(_:)`` so Python can pick it up.
///
/// App Store constraint: recording runs in foreground + background (with
/// entitlement). Inference only after the user stops recording and the app
/// is foregrounded — this actor enforces that by not calling Python until
/// ``stop()`` is called and the flush is complete.
@MainActor
final class AudioRecorder: ObservableObject {

    @Published private(set) var isRecording = false
    @Published private(set) var levelDB: Float = -60.0   // for waveform visualisation

    private let engine       = AVAudioEngine()
    private var pcmBuffer    = [Int16]()
    private let bufferLock   = NSLock()
    private let sampleRate   = 16_000.0
    private let outputFormat = AVAudioFormat(
        commonFormat: .pcmFormatInt16,
        sampleRate: 16_000,
        channels: 1,
        interleaved: true
    )!

    // MARK: - Public

    func start() throws {
        guard !isRecording else { return }

        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord,
                                mode: .measurement,
                                options: [.defaultToSpeaker, .allowBluetooth])
        try session.setPreferredSampleRate(sampleRate)
        try session.setActive(true, options: .notifyOthersOnDeactivation)

        let inputNode = engine.inputNode
        let inputFormat = inputNode.outputFormat(forBus: 0)

        // Converter: device native format → 16kHz Int16 mono
        guard let converter = AVAudioConverter(from: inputFormat, to: outputFormat) else {
            throw AudioRecorderError.converterCreationFailed
        }

        inputNode.installTap(onBus: 0, bufferSize: 4096, format: inputFormat) { [weak self] buf, _ in
            self?.process(buf, converter: converter)
        }

        try engine.start()
        bufferLock.lock(); pcmBuffer.removeAll(); bufferLock.unlock()
        isRecording = true
    }

    func stop() {
        guard isRecording else { return }
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        isRecording = false

        Task { await flushToWAV() }
    }

    // MARK: - Private

    private func process(_ buf: AVAudioPCMBuffer, converter: AVAudioConverter) {
        // Compute level for waveform display
        if let channelData = buf.floatChannelData?[0] {
            let count = Int(buf.frameLength)
            var rms: Float = 0
            for i in 0..<count { rms += channelData[i] * channelData[i] }
            rms = sqrtf(rms / Float(count))
            let db = rms > 0 ? 20 * log10f(rms) : -60.0
            Task { @MainActor [weak self] in self?.levelDB = db }
        }

        // Convert to 16kHz Int16
        let outCapacity = AVAudioFrameCount(
            Double(buf.frameLength) * sampleRate / buf.format.sampleRate
        )
        guard let outBuf = AVAudioPCMBuffer(pcmFormat: outputFormat, frameCapacity: outCapacity) else { return }
        var error: NSError?
        converter.convert(to: outBuf, error: &error) { _, outStatus in
            outStatus.pointee = .haveData
            return buf
        }
        guard error == nil, let data = outBuf.int16ChannelData?[0] else { return }
        let frames = Int(outBuf.frameLength)
        bufferLock.lock()
        pcmBuffer.append(contentsOf: UnsafeBufferPointer(start: data, count: frames))
        bufferLock.unlock()
    }

    private func flushToWAV() async {
        bufferLock.lock()
        let samples = pcmBuffer
        pcmBuffer.removeAll()
        bufferLock.unlock()

        guard !samples.isEmpty else { return }

        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("vakya_\(Date().timeIntervalSince1970).wav")

        do {
            let data = try buildWAV(samples: samples, sampleRate: Int(sampleRate))
            try data.write(to: url)
            VakyaBridge.shared.wavReady(url.path)
        } catch {
            print("[AudioRecorder] WAV flush failed: \(error)")
        }
    }

    private func buildWAV(samples: [Int16], sampleRate: Int) throws -> Data {
        var data = Data()
        let pcmBytes = samples.count * 2
        let totalData = pcmBytes + 36
        let byteRate  = sampleRate * 2

        func write<T: FixedWidthInteger>(_ v: T) {
            withUnsafeBytes(of: v.littleEndian) { data.append(contentsOf: $0) }
        }
        data.append(contentsOf: "RIFF".utf8)
        write(Int32(totalData))
        data.append(contentsOf: "WAVE".utf8)
        data.append(contentsOf: "fmt ".utf8)
        write(Int32(16))
        write(Int16(1))                   // PCM
        write(Int16(1))                   // mono
        write(Int32(sampleRate))
        write(Int32(byteRate))
        write(Int16(2))                   // block align
        write(Int16(16))                  // bits
        data.append(contentsOf: "data".utf8)
        write(Int32(pcmBytes))
        samples.forEach { write($0) }
        return data
    }
}

enum AudioRecorderError: Error {
    case converterCreationFailed
}
