import SwiftUI
import AppKit
import MetalKit
import CedaCore

final class CedaDelegate: NSObject, NSApplicationDelegate {
    weak var store: WorkbenchStore?
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ notification: Notification) { Task { @MainActor in store?.shutdown() } }
}
@main struct CedaNativeApp: App {
    @StateObject private var store = WorkbenchStore()
    @NSApplicationDelegateAdaptor(CedaDelegate.self) private var delegate
    init() {
        let arguments = CommandLine.arguments
        if let index = arguments.firstIndex(of: "--check-contract"), arguments.count > index+1 {
            do { let board = try BoardDocument.read(URL(fileURLWithPath: arguments[index+1]).appendingPathComponent("board.json")); print("Validated native board: \(board.board.pad_count) pads / \(board.objects.count) objects"); exit(0) }
            catch { fputs("\(error.localizedDescription)\n",stderr); exit(2) }
        }
        if let index = arguments.firstIndex(of: "--metal-snapshot"), arguments.count > index+2 {
            do {
                let folder = URL(fileURLWithPath: arguments[index+1]); let board = try BoardDocument.read(folder.appendingPathComponent("board.json"))
                let (mesh,data) = try MeshDocument.read(folder,boardHash: board.board.sha256)
                guard let device = MTLCreateSystemDefaultDevice() else { throw ContractError.invalid("没有 Metal 设备") }
                let renderer = try MetalRenderer(device: device); try renderer.load(data,count: mesh.vertex_count); renderer.span = Float(mesh.span_mm)
                try renderer.snapshot(width: 1400,height: 800).write(to: URL(fileURLWithPath: arguments[index+2]),options: .atomic)
                print("Metal verified: \(device.name), \(mesh.vertex_count) vertices, \(mesh.models_loaded)/\(mesh.models_total) model references"); exit(0)
            } catch { fputs("\(error.localizedDescription)\n",stderr); exit(2) }
        }
    }
    var body: some Scene {
        Window("Ceda · PCB 工作台",id: "workbench") {
            WorkbenchView(store: store).onAppear {
                delegate.store = store
                let arguments = CommandLine.arguments
                if arguments.contains("--demo") { store.demo() }
                else if let index = arguments.firstIndex(of: "--board"), arguments.count > index+1 { store.load(URL(fileURLWithPath: arguments[index+1])) }
            }
        }.defaultSize(width: 1440,height: 930).windowToolbarStyle(.unifiedCompact)
        .commands {
            CommandGroup(replacing: .newItem) { Button("导入 PCB…",action: store.chooseBoard).keyboardShortcut("o").disabled(store.busy); Button("打开合成演示板",action: store.demo).disabled(store.busy) }
            CommandGroup(replacing: .saveItem) { Button("打开工况…",action: store.openConfig).disabled(store.document == nil || store.busy); Button("保存工况…",action: store.saveConfig).keyboardShortcut("s").disabled(store.document == nil || store.busy) }
            CommandMenu("分析") { Button("开始供电分析",action: store.analyze).keyboardShortcut("r").disabled(store.busy || store.document == nil || store.blocked); Button("取消计算",action: store.cancel).disabled(!store.busy); Divider(); Button("模型与分析诊断") { store.diagnosticsVisible = true } }
        }
    }
}
