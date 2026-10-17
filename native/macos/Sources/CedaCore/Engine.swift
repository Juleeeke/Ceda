import Foundation

public struct EngineLocation: Sendable {
    public var executable: URL; public var prefix: [String]; public var workingDirectory: URL?
    public init(executable: URL, prefix: [String] = [], workingDirectory: URL? = nil) {
        self.executable = executable; self.prefix = prefix; self.workingDirectory = workingDirectory
    }
    public static func discover(bundle: Bundle = .main) throws -> Self {
        if let resource = bundle.resourceURL {
            let binary = resource.appendingPathComponent("Engine/CedaEngine/CedaEngine")
            if FileManager.default.isExecutableFile(atPath: binary.path) { return Self(executable: binary) }
        }
        var candidates: [URL] = []
        if let root = ProcessInfo.processInfo.environment["CEDA_PROJECT_ROOT"] { candidates.append(URL(fileURLWithPath: root)) }
        var current = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        for _ in 0..<6 { candidates.append(current); current.deleteLastPathComponent() }
        for root in candidates {
            let python = root.appendingPathComponent(".venv/bin/python")
            if FileManager.default.isExecutableFile(atPath: python.path), FileManager.default.fileExists(atPath: root.appendingPathComponent("src/ceda").path) {
                return Self(executable: python, prefix: ["-m", "ceda"], workingDirectory: root)
            }
        }
        throw ContractError.invalid("找不到 Ceda 仿真内核。请使用完整应用包，或在仓库根目录运行。")
    }
}
public final class EngineJob: @unchecked Sendable {
    private let lock = NSLock(); private var process: Process?; private var cancelled = false
    public init() {}
    public func cancel() {
        lock.lock(); cancelled = true; let child = process; lock.unlock()
        if let child, child.isRunning { child.terminate() }
    }
    private func isCancelled() -> Bool { lock.lock(); defer { lock.unlock() }; return cancelled }
    public func run(_ location: EngineLocation, arguments: [String], progress: @escaping @Sendable (String) -> Void) async throws {
        try await withTaskCancellationHandler(operation: {
            try await Task.detached(priority: .userInitiated) { [self] in
                try execute(location, arguments: arguments, progress: progress)
            }.value
        }, onCancel: { self.cancel() })
    }
    private func execute(_ location: EngineLocation, arguments: [String], progress: @escaping @Sendable (String) -> Void) throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("ceda-process-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let logURL = folder.appendingPathComponent("output.log")
        _ = FileManager.default.createFile(atPath: logURL.path, contents: nil)
        let writer = try FileHandle(forWritingTo: logURL); defer { try? writer.close() }
        let reader = try FileHandle(forReadingFrom: logURL); defer { try? reader.close() }
        let child = Process(); child.executableURL = location.executable; child.arguments = location.prefix + arguments
        child.currentDirectoryURL = location.workingDirectory
        child.standardOutput = writer; child.standardError = writer
        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONUNBUFFERED"] = "1"; environment["QT_QPA_PLATFORM"] = "offscreen"
        child.environment = environment
        lock.lock(); process = child; let stop = cancelled; lock.unlock()
        defer {
            if child.isRunning { kill(child.processIdentifier,SIGKILL); child.waitUntilExit() }
            lock.lock(); process = nil; lock.unlock()
        }
        if stop { throw CancellationError() }
        try child.run()
        var pending = Data(); var tail = ""; var cancellationDate: Date?
        func readProgress() throws {
            if let bytes = try reader.readToEnd(), !bytes.isEmpty { pending.append(bytes) }
            while let newline = pending.firstIndex(of: 10) {
                let line = String(decoding: pending[..<newline], as: UTF8.self); pending.removeSubrange(...newline)
                tail = String((tail + "\n" + line).suffix(8000))
                if let data = line.data(using: .utf8), let event = try? JSONSerialization.jsonObject(with: data) as? [String: Any], let message = event["message"] as? String { progress(message) }
            }
        }
        while child.isRunning {
            try readProgress()
            if isCancelled() {
                if cancellationDate == nil { cancellationDate = Date(); child.terminate() }
                if let date = cancellationDate, Date().timeIntervalSince(date) > 3 { kill(child.processIdentifier,SIGKILL) }
            }
            Thread.sleep(forTimeInterval: 0.1)
        }
        child.waitUntilExit(); try readProgress()
        if isCancelled() { throw CancellationError() }
        guard child.terminationReason == .exit && child.terminationStatus == 0 else { throw ContractError.invalid(tail.isEmpty ? "内核异常退出：\(child.terminationStatus)" : tail) }
    }
}
