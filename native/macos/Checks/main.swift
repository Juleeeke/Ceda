import Foundation
import CedaCore

final class Messages: @unchecked Sendable {
    let lock = NSLock(); private var values: [String] = []
    func append(_ value: String) { lock.lock(); values.append(value); lock.unlock() }
    func contains(_ value: String) -> Bool { lock.lock(); defer { lock.unlock() }; return values.contains(value) }
}
@main struct ContractChecks {
    static func main() async {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("ceda-checks-\(UUID().uuidString)")
        var passed = 0
        func check(_ condition: @autoclosure () -> Bool,_ message: String) throws { guard condition() else { throw ContractError.invalid(message) }; passed += 1 }
        func rejected(_ action: () throws -> Void) throws { do { try action() } catch { passed += 1; return }; throw ContractError.invalid("Invalid contract was accepted") }
        defer { try? FileManager.default.removeItem(at: root) }
        do {
            try FileManager.default.createDirectory(at: root,withIntermediateDirectories: true)
            let path = root.appendingPathComponent("board.json")
            func document(_ schema: Int = 1,_ point: String = "[0,0]") -> String { """
            {"schema_version":\(schema),"board":{"path":"board.kicad_pcb","sha256":"abc","layers":[{"name":"F.Cu","thickness_mm":0.035}],"pads":[],"pad_count":0,"via_count":0,"components":{},"issues":[]},"bounds_mm":[0,0,10,5],"outline":[],"objects":[{"id":0,"kind":"copper","polygons":[{"rings":[[\(point),[10,0],[0,5]]]}],"layer":"F.Cu","layers":["F.Cu"],"net":"GND"}],"texts":[],"warnings":[]}
            """ }
            try Data(document().utf8).write(to: path)
            let board = try BoardDocument.read(path); try check(board.objects[0].polygons[0].rings[0].count == 3,"Geometry lost")
            try Data(document(99).utf8).write(to: path); try rejected { _ = try BoardDocument.read(path) }
            try Data(document(1,"[0]").utf8).write(to: path); try rejected { _ = try BoardDocument.read(path) }
            let transform = ViewportTransform(bounds: [10,20,60,50],width: 900,height: 500,zoom: 3,panX: 53,panY: -72)
            let p = transform.screen([22.25,31.75]); let q = transform.board(x: p.0,y: p.1)
            try check(abs(q.0-22.25) < 1e-9 && abs(q.1-31.75) < 1e-9,"Pan/zoom round trip failed")
            let mesh = """
            {"schema_version":1,"vertices_file":"vertices.bin","vertex_count":3,"stride_bytes":40,"center_mm":[0,0,0],"span_mm":10,"categories":["substrate"],"models_loaded":0,"models_total":0,"warnings":[],"board_sha256":"abc"}
            """
            try Data(mesh.utf8).write(to: root.appendingPathComponent("mesh.json"))
            try Data(count: 100).write(to: root.appendingPathComponent("vertices.bin")); try rejected { _ = try MeshDocument.read(root,boardHash: "abc") }
            try Data(count: 120).write(to: root.appendingPathComponent("vertices.bin")); try rejected { _ = try MeshDocument.read(root,boardHash: "other") }
            let (_,data) = try MeshDocument.read(root,boardHash: "abc"); try check(data.count == 120,"Valid mesh rejected")
            let messages = Messages()
            try await EngineJob().run(EngineLocation(executable: URL(fileURLWithPath: "/bin/echo")),arguments: ["{\"event\":\"progress\",\"message\":\"实际进度\"}"]) { messages.append($0) }
            try check(messages.contains("实际进度"),"Worker progress lost")
            do { try await EngineJob().run(EngineLocation(executable: URL(fileURLWithPath: "/usr/bin/false")),arguments: []) { _ in }; throw ContractError.invalid("Failed worker accepted") }
            catch let error as ContractError { if error.localizedDescription == "Failed worker accepted" { throw error }; passed += 1 }
            let job = EngineJob(); let start = Date()
            let task = Task { try await job.run(EngineLocation(executable: URL(fileURLWithPath: "/bin/sleep")),arguments: ["20"]) { _ in } }
            try await Task.sleep(nanoseconds: 200_000_000); job.cancel()
            do { try await task.value; throw ContractError.invalid("Cancelled worker accepted") } catch is CancellationError { passed += 1 }
            try check(Date().timeIntervalSince(start) < 5,"Cancellation did not stop own child")
            print("Ceda native contract/process checks: \(passed) passed")
        } catch { fputs("Native checks failed: \(error.localizedDescription)\n",stderr); exit(1) }
    }
}
