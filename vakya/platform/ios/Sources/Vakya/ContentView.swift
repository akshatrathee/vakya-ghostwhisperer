import SwiftUI
import AVFoundation

/// Main recording UI.
///
/// UI states:
///   idle       — large mic button, last transcript shown
///   recording  — waveform + level meter, stop button
///   processing — spinner "Transcribing…"
///   error      — error message + retry button
struct ContentView: View {

    @EnvironmentObject private var bridge: VakyaBridge
    @StateObject private var recorder = AudioRecorder()
    @State private var showSettings = false
    @State private var enhancedCleanup = false

    var body: some View {
        NavigationStack {
            ZStack {
                Color.black.ignoresSafeArea()

                VStack(spacing: 24) {
                    header
                    transcriptArea
                    Spacer()
                    statusLabel
                    recordButton
                }
                .padding()
            }
            .navigationTitle("")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button { showSettings = true } label: {
                        Image(systemName: "gearshape")
                            .foregroundColor(.white)
                    }
                }
            }
            .sheet(isPresented: $showSettings) {
                SettingsSheet(enhancedCleanup: $enhancedCleanup)
                    .environmentObject(bridge)
            }
        }
        .preferredColorScheme(.dark)
        .onChange(of: enhancedCleanup) { _, enabled in
            bridge.setEnhancedCleanup(enabled)
        }
    }

    // MARK: - Sub-views

    private var header: some View {
        HStack {
            Text("Vakya")
                .font(.system(size: 28, weight: .bold, design: .rounded))
                .foregroundColor(.white)
            Spacer()
        }
    }

    private var transcriptArea: some View {
        ScrollView {
            Text(bridge.lastTranscript.isEmpty ? "Your transcript will appear here…" : bridge.lastTranscript)
                .font(.body)
                .foregroundColor(bridge.lastTranscript.isEmpty ? .gray : .white)
                .frame(maxWidth: .infinity, alignment: .leading)
                .lineSpacing(6)
                .padding()
        }
        .frame(maxWidth: .infinity, minHeight: 200)
        .background(Color.white.opacity(0.05))
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    private var statusLabel: some View {
        Group {
            if let err = bridge.lastError {
                Text(err)
                    .foregroundColor(.red)
                    .font(.caption)
                    .multilineTextAlignment(.center)
            } else if bridge.isProcessing {
                Label("Transcribing…", systemImage: "waveform")
                    .foregroundColor(.purple)
            } else if recorder.isRecording {
                WaveformView(level: recorder.levelDB)
            } else {
                Text("Tap to record")
                    .foregroundColor(.gray)
                    .font(.subheadline)
            }
        }
        .frame(height: 44)
    }

    private var recordButton: some View {
        Button {
            if recorder.isRecording {
                recorder.stop()
            } else {
                Task { try? await recorder.start() }
            }
        } label: {
            ZStack {
                Circle()
                    .fill(recorder.isRecording ? Color.red : Color.purple)
                    .frame(width: 80, height: 80)
                Image(systemName: recorder.isRecording ? "stop.fill" : "mic.fill")
                    .font(.system(size: 32))
                    .foregroundColor(.white)
            }
        }
        .disabled(bridge.isProcessing)
        .animation(.easeInOut(duration: 0.2), value: recorder.isRecording)
        .padding(.bottom, 32)
    }
}

// MARK: - WaveformView

struct WaveformView: View {
    let level: Float    // -60…0 dB

    private var normalised: CGFloat {
        CGFloat(max(0, min(1, (level + 60) / 60)))
    }

    var body: some View {
        HStack(spacing: 3) {
            ForEach(0..<20, id: \.self) { i in
                let h = CGFloat.random(in: 4...(4 + normalised * 36))
                RoundedRectangle(cornerRadius: 2)
                    .fill(Color.purple)
                    .frame(width: 4, height: h)
                    .animation(.easeOut(duration: 0.08), value: normalised)
            }
        }
    }
}

// MARK: - SettingsSheet

struct SettingsSheet: View {
    @Binding var enhancedCleanup: Bool
    @EnvironmentObject private var bridge: VakyaBridge
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section("Cleanup engine") {
                    Toggle("Enhanced (Phi-3 Mini)", isOn: $enhancedCleanup)
                    if enhancedCleanup {
                        Text("Uses ~1.8 GB RAM. Slower but more accurate punctuation and formatting.")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}
