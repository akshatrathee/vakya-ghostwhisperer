import SwiftUI
import PythonKit

@main
struct VakyaApp: App {

    init() {
        // Initialise BeeWare Python runtime before any view renders.
        // Python.shared.initialize() sets sys.path to the app bundle's
        // Python/ directory where vakya/ package lives.
        Python.shared.initialize()

        let fm = FileManager.default
        let docs   = fm.urls(for: .documentDirectory,    in: .userDomainMask)[0].path
        let support = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].path

        VakyaBridge.shared.initialise(configDir: docs, modelsDir: support)
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(VakyaBridge.shared)
        }
    }
}
