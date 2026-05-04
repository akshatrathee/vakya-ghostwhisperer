import Foundation
import PythonKit   // BeeWare ships PythonKit; rubicon-objc is the lower-level layer

/// Singleton bridge between Swift and the Python ``iOSPipelineBridge``.
///
/// ``VakyaBridge`` is the single point of contact between Swift and Python.
/// All heavy inference stays on the Python side. Swift only:
///   - passes the WAV path after ``AudioRecorder`` flushes
///   - receives a JSON string back and decodes it
///   - updates SwiftUI state on the main actor
///
/// BeeWare / PythonKit integration:
///   Python.shared.initialize() is called in VakyaApp.init() before any
///   PythonObject call.
@MainActor
final class VakyaBridge: ObservableObject {

    static let shared = VakyaBridge()

    @Published private(set) var isProcessing = false
    @Published private(set) var lastTranscript = ""
    @Published private(set) var lastError: String? = nil

    private var bridge: PythonObject?

    // MARK: - Init

    func initialise(configDir: String, modelsDir: String) {
        Task.detached(priority: .userInitiated) {
            let py = Python.shared
            let module = py.import("vakya.platform.ios.main")
            let b = module.init(configDir, modelsDir, false)
            await MainActor.run { [weak self] in
                self?.bridge = b
            }
        }
    }

    // MARK: - Called by AudioRecorder after WAV flush

    func wavReady(_ wavPath: String) {
        guard let bridge else { return }
        isProcessing = true
        lastError = nil

        Task.detached(priority: .userInitiated) { [weak self] in
            let jsonStr = String(bridge.transcribe(wavPath, true))!
            let result  = TranscribeResult.decode(from: jsonStr)
            await MainActor.run { [weak self] in
                self?.isProcessing = false
                if let err = result.error {
                    self?.lastError = err
                } else {
                    self?.lastTranscript = result.text
                    UIPasteboard.general.string = result.text
                }
            }
        }
    }

    // MARK: - Settings

    func setEnhancedCleanup(_ enabled: Bool) {
        bridge?.set_enhanced_cleanup(enabled)
    }

    func warmUp() {
        bridge?.warm_up()
    }

    // MARK: - ObjC visibility (for rubicon-objc calls from Python)

    @objc func startCapture()  { /* AudioRecorder.start() called from ContentView */ }
    @objc func stopCapture()   { /* AudioRecorder.stop()  called from ContentView */ }
}

// MARK: - Result types

struct TranscribeResult: Decodable {
    let text: String
    let language: String
    let duration_s: Double
    let engine: String
    let error: String?

    static func decode(from json: String) -> TranscribeResult {
        let data = json.data(using: .utf8) ?? Data()
        return (try? JSONDecoder().decode(TranscribeResult.self, from: data))
               ?? TranscribeResult(text: "", language: "en",
                                   duration_s: 0, engine: "", error: "JSON parse error")
    }
}

struct SynthesiseResult: Decodable {
    let wav_path: String?
    let duration_s: Double
    let error: String?
}
