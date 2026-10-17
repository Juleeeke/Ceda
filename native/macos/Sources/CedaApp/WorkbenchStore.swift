import SwiftUI
import AppKit
import UniformTypeIdentifiers
import CedaCore

struct LoadInput: Codable, Identifiable {
    var positive: String; var negative: String; var current_a: Double; var minimum_voltage_v: Double?
    var label: String? = nil
    var id: String { positive + "|" + negative }
}
enum WorkspacePage: String, CaseIterable {
    case overview = "板卡概览", analysis = "供电分析", materials = "叠层与材料", models = "器件模型", report = "分析报告"
    var icon: String { switch self { case .overview: return "square.stack.3d.up"; case .analysis: return "waveform.path.ecg"; case .materials: return "square.3.layers.3d"; case .models: return "shippingbox"; case .report: return "doc.text" } }
}
@MainActor final class WorkbenchStore: ObservableObject {
    @Published var document: BoardDocument?; @Published var result: AnalysisResult?
    @Published var mesh: MeshDocument?; @Published var vertices: Data?
    @Published var meshRevision = UUID()
    @Published var page: WorkspacePage = .overview; @Published var is3D = false
    @Published var field: ViewField = .geometry; @Published var layer = "F.Cu"
    @Published var lightCanvas = false; @Published var showGrid = true; @Published var showLabels = true; @Published var showMesh = false
    @Published var visibleLayers: Set<String> = ["F.Cu","B.Cu","F.SilkS","B.SilkS","Edge.Cuts"]
    @Published var categories: Set<Int> = Set(0..<6)
    @Published var zoom2D = 1.0; @Published var pan2D = CGSize.zero
    @Published var zoom3D: Float = 1; @Published var yaw: Float = -65; @Published var tilt: Float = 48; @Published var pan3D = CGSize.zero
    @Published var sourceP = ""; @Published var sourceN = ""; @Published var voltage = 3.3
    @Published var loadP = ""; @Published var loadN = ""; @Published var current = 0.1; @Published var minimum = 3.0
    @Published var meshSize = 0.5; @Published var copperThickness = 0.0; @Published var plating = 0.0; @Published var refine = true
    @Published var loads: [LoadInput] = []; @Published var selectedPad: String?
    @Published var busy = false; @Published var status = "本地工作空间 · 导入 PCB 开始检查"
    @Published var log: [String] = []; @Published var error: String?; @Published var diagnosticsVisible = false
    @Published var cursor = "单位 mm"; @Published var modelLibrary: URL?
    private var configuration: [String: Any] = [:]
    private var operationID = UUID(); private var meshQueued = false
    private let temporary = FileManager.default.temporaryDirectory.appendingPathComponent("ceda-swiftui-\(UUID().uuidString)")
    private var currentFolder: URL?; private var reportFolder: URL?; private var job: EngineJob?; private var operation: Task<Void, Never>?
    var filename: String { document.map { URL(fileURLWithPath: $0.board.path).lastPathComponent } ?? "未导入板卡" }
    var blocked: Bool { document?.board.issues.contains(where: { $0.severity == "error" }) ?? false }
    var selectedDescription: String {
        guard let id = selectedPad else { return "" }
        let matches = document?.board.pads.filter { $0.id == id } ?? []
        guard matches.count == 1, let pad = matches.first else { return "\(id) · \(matches.count) 个同号焊盘\n当前求解端口要求唯一焊盘，未自动选择其中一个。" }
        return "\(pad.id) / \(pad.net)\n\(pad.layers.joined(separator: ", "))\nX \(pad.x_mm.formatted()) · Y \(pad.y_mm.formatted()) mm"
    }
    var fieldLegend: String {
        if is3D { return "三维实体检查 · 未叠加场结果" }
        if field == .geometry || result == nil { return "文件几何 · \(layer) · 单位 mm" }
        guard let mesh = result?.mesh else { return "尚未求解" }
        let indices = mesh.triangles.indices.filter { mesh.triangle_keys[$0][1] == layer }
        let values = indices.map { field == .current ? mesh.current_density_a_mm2[$0] : mesh.triangles[$0].map { mesh.voltage_v[$0] }.reduce(0,+)/3 }
        guard let low = values.min(), let high = values.max() else { return "当前层没有已求解数据" }
        return String(format: "%.4g → %.4g ",low,high)+(field == .current ? "A/mm²" : "V，相对源负端")+" · 仅已求解网络"
    }
    var verdict: String {
        guard let result else { return blocked ? "导入预检有阻断项" : document == nil ? "等待导入" : "几何已导入" }
        return result.verdict == "fail" ? "供电低于设定值" : result.verdict == "pass_scoped" ? "当前 DC 工况通过" : "数值结果待核实"
    }
    var diagnosticLines: [String] {
        (document?.board.issues.map(\.message) ?? []) + (document?.warnings ?? []) + (mesh?.warnings ?? []) + (result?.unverified ?? [])
    }
    func chooseBoard() {
        let panel = NSOpenPanel(); panel.allowedContentTypes = [UTType(filenameExtension: "kicad_pcb") ?? .data]; panel.canChooseDirectories = false
        if panel.runModal() == .OK, let url = panel.url { load(url) }
    }
    func load(_ url: URL, demo: Bool = false) {
        guard !busy else { return }
        perform("读取实际 PCB 几何") { [self] location, job in
            let folder = temporary.appendingPathComponent(UUID().uuidString)
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            try await job.run(location, arguments: ["native-export",url.path,"--output",folder.path], progress: progress)
            let value = try BoardDocument.read(folder.appendingPathComponent("board.json"))
            currentFolder = folder; document = value; result = nil; mesh = nil; vertices = nil; reportFolder = nil; selectedPad = nil
            configuration = [:]; loads = []; is3D = false; field = .geometry; page = .overview
            layer = value.board.layers.first?.name ?? "F.Cu"; visibleLayers.formUnion(value.board.layers.map(\.name)); fit()
            let pads = value.board.pads
            sourceP = pads.first(where: { !$0.net.uppercased().contains("GND") && !$0.net.isEmpty })?.id ?? pads.first?.id ?? ""
            sourceN = pads.first(where: { $0.net.uppercased().contains("GND") })?.id ?? pads.last?.id ?? ""
            loadP = sourceP; loadN = sourceN
            voltage = 3.3; current = 0.1; minimum = 3; meshSize = 0.5; copperThickness = 0; plating = 0; refine = true
            if demo, let config = demoURL("demo.json") { try applyConfiguration(config) }
            status = demo ? "合成演示板 · 3.3 V / 0.5 A · 用于数值回归" : blocked ? "几何可查看；导入预检有阻断项，不能开始求解" : "几何已导入，请确认电源、负载与材料"
        }
    }
    private func demoURL(_ name: String) -> URL? {
        if let root = Bundle.main.resourceURL {
            let url = root.appendingPathComponent("Demo/\(name)"); if FileManager.default.fileExists(atPath: url.path) { return url }
        }
        if let location = try? EngineLocation.discover(), let root = location.workingDirectory { return root.appendingPathComponent("src/ceda/resources/\(name)") }
        return nil
    }
    func demo() { if let url = demoURL("demo.kicad_pcb") { load(url, demo: true) } else { error = "演示文件不存在" } }
    func navigate(_ next: WorkspacePage) {
        page = next
        switch next {
        case .overview: is3D = false; field = .geometry
        case .analysis: is3D = false; field = .current
        case .models: is3D = true; buildMesh()
        case .report: openReport()
        case .materials: break
        }
    }
    func chooseLibrary() {
        let panel = NSOpenPanel(); panel.canChooseDirectories = true; panel.canChooseFiles = false
        panel.message = "选择包含 .3dshapes 文件夹的 KiCad 三维模型库根目录"
        if panel.runModal() == .OK, let url = panel.url { modelLibrary = url; mesh = nil; vertices = nil; if is3D { buildMesh() } }
    }
    func buildMesh() {
        if busy { meshQueued = true; return }
        guard mesh == nil, let board = document, let folder = currentFolder else { return }
        perform("读取板体和实际元件模型") { [self] location, job in
            var args = ["native-mesh",board.board.path,"--output",folder.path,"--expected-board-sha",board.board.sha256]
            if let modelLibrary { args += ["--model-library",modelLibrary.path] }
            try await job.run(location, arguments: args, progress: progress)
            let (metadata, data) = try MeshDocument.read(folder, boardHash: board.board.sha256)
            mesh = metadata; vertices = data; meshRevision = UUID(); fit()
            status = "模型引用 \(metadata.models_loaded)/\(metadata.models_total) · \(metadata.warnings.count) 项提示"
        }
    }
    func addLoad() {
        guard loadP != loadN, current.isFinite, current > 0, minimum.isFinite, minimum >= 0 else { error = "负载正负端应不同，电流必须大于 0，最低电压不能为负。"; return }
        loads.append(LoadInput(positive: loadP, negative: loadN, current_a: current, minimum_voltage_v: minimum > 0 ? minimum : nil))
    }
    private func configData() throws -> Data {
        guard !sourceP.isEmpty, sourceP != sourceN, voltage.isFinite, voltage > 0, !loads.isEmpty else {
            throw ContractError.invalid("请选择不同的电源正负端，并添加至少一个负载。")
        }
        guard meshSize.isFinite, meshSize > 0, copperThickness.isFinite, copperThickness >= 0,
              plating.isFinite, plating >= 0, loads.allSatisfy({ $0.current_a.isFinite && $0.current_a > 0 && $0.positive != $0.negative }) else {
            throw ContractError.invalid("网格、铜厚、镀层和负载参数无效")
        }
        var data = configuration; var settings = data["settings"] as? [String: Any] ?? [:]
        settings["mesh_size_mm"] = meshSize; settings["mesh_refinement"] = refine
        settings["copper_thickness_mm"] = copperThickness > 0 ? copperThickness as Any : NSNull()
        settings["via_plating_mm"] = plating > 0 ? plating as Any : NSNull()
        data["schema_version"] = 1; data["name"] = data["name"] ?? filename
        data["sources"] = [["positive": sourceP,"negative": sourceN,"voltage_v": voltage]]
        data["loads"] = try JSONSerialization.jsonObject(with: JSONEncoder().encode(loads)); data["settings"] = settings
        return try JSONSerialization.data(withJSONObject: data, options: [.prettyPrinted,.sortedKeys])
    }
    func analyze() {
        guard !busy, let board = document, let folder = currentFolder else { return }
        guard !blocked else { diagnosticsVisible = true; return }
        do {
            let config = folder.appendingPathComponent("scenario.json"); try configData().write(to: config, options: .atomic)
            result = nil
            perform("开始规定工况 DC 分析") { [self] location, job in
                let output = folder.appendingPathComponent("run-\(UUID().uuidString)")
                try await job.run(location, arguments: ["worker",board.board.path,"--config",config.path,"--output",output.path,"--expected-board-sha",board.board.sha256], progress: progress)
                result = try JSONDecoder().decode(AnalysisResult.self, from: Data(contentsOf: output.appendingPathComponent("result.json")))
                reportFolder = output; if !is3D { field = .current }; status = verdict
            }
        } catch { self.error = error.localizedDescription }
    }
    func openConfig() {
        guard document != nil else { return }
        let panel = NSOpenPanel(); panel.allowedContentTypes = [.json]
        if panel.runModal() == .OK, let url = panel.url { do { try applyConfiguration(url) } catch { self.error = error.localizedDescription } }
    }
    private func applyConfiguration(_ url: URL) throws {
        guard let data = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any],
              let sources = data["sources"] as? [[String: Any]], sources.count == 1,
              let source = sources.first, let p = source["positive"] as? String, let n = source["negative"] as? String,
              let v = source["voltage_v"] as? Double, let rawLoads = data["loads"] else { throw ContractError.invalid("工况无效；原生界面当前支持单电源工况") }
        guard (data["schema_version"] as? Int ?? 1) == 1 else { throw ContractError.invalid("不支持的工况版本") }
        let imported = try JSONDecoder().decode([LoadInput].self, from: JSONSerialization.data(withJSONObject: rawLoads))
        let ids = Set(document?.board.pads.map(\.id) ?? [])
        guard [p,n].allSatisfy(ids.contains), imported.allSatisfy({ ids.contains($0.positive) && ids.contains($0.negative) }) else {
            throw ContractError.invalid("工况引用的焊盘不属于当前板卡")
        }
        configuration = data; sourceP = p; sourceN = n; voltage = v; loads = imported
        if let first = imported.first { loadP = first.positive; loadN = first.negative; current = first.current_a; minimum = first.minimum_voltage_v ?? 0 }
        let settings = data["settings"] as? [String: Any] ?? [:]
        meshSize = settings["mesh_size_mm"] as? Double ?? 0.5; copperThickness = settings["copper_thickness_mm"] as? Double ?? 0
        plating = settings["via_plating_mm"] as? Double ?? 0; refine = settings["mesh_refinement"] as? Bool ?? true
    }
    func saveConfig() {
        do { let data = try configData(); let panel = NSSavePanel(); panel.allowedContentTypes = [.json]; panel.nameFieldStringValue = "scenario.json"
            if panel.runModal() == .OK, let url = panel.url { try data.write(to: url, options: .atomic) }
        } catch { self.error = error.localizedDescription }
    }
    func exportReport() {
        guard let source = reportFolder else { return }
        let panel = NSOpenPanel(); panel.canChooseDirectories = true; panel.canChooseFiles = false; panel.message = "选择报告导出目录"
        if panel.runModal() == .OK, let parent = panel.url {
            do { let destination = parent.appendingPathComponent("Ceda-\(Int(Date().timeIntervalSince1970))")
                try FileManager.default.copyItem(at: source, to: destination); NSWorkspace.shared.open(destination.appendingPathComponent("report.html"))
            } catch { self.error = error.localizedDescription }
        }
    }
    func openReport() { if let reportFolder { NSWorkspace.shared.open(reportFolder.appendingPathComponent("report.html")) } }
    func fit() { zoom2D = 1; pan2D = .zero; zoom3D = 1; pan3D = .zero }
    func pose(_ value: String) { is3D = true; buildMesh(); yaw = value == "iso" ? -65 : 0; tilt = value == "top" ? 0 : value == "bottom" ? 180 : 48; fit() }
    func selectPad(_ identifier: String) { selectedPad = identifier; if document?.board.pads.filter({ $0.id == identifier }).count == 1 { loadP = identifier } }
    func cancel() { operation?.cancel(); job?.cancel() }
    func shutdown() { cancel() }
    private var progress: @Sendable (String) -> Void {
        let expected = operationID
        return { [weak self] message in Task { @MainActor in
            guard let self, self.busy, self.operationID == expected else { return }
            self.status = message; self.log.append(message); if self.log.count > 500 { self.log.removeFirst() }
        } }
    }
    private func perform(_ title: String, action: @escaping @MainActor (EngineLocation,EngineJob) async throws -> Void) {
        guard !busy else { return }; operationID = UUID(); busy = true; error = nil; status = title; log = [title]
        let active = EngineJob(); job = active
        operation = Task { [self] in
            defer {
                busy = false; job = nil; operation = nil
                if meshQueued { meshQueued = false; if is3D && !Task.isCancelled && error == nil { Task { [weak self] in self?.buildMesh() } } }
            }
            do { try await action(EngineLocation.discover(),active) }
            catch is CancellationError { status = "已取消；未产生通过结论" }
            catch { self.error = error.localizedDescription; status = "操作未完成，详见诊断" }
        }
    }
}
