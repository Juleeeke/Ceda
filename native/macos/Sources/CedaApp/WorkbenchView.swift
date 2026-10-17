import SwiftUI
import CedaCore

private let ink = Color(red: 0.15,green: 0.17,blue: 0.19)
struct WorkbenchView: View {
    @ObservedObject var store: WorkbenchStore
    var body: some View {
        HStack(spacing: 0) {
            sidebar.frame(width: 200)
            Divider()
            VStack(spacing: 0) {
                header
                Divider()
                HStack(spacing: 0) { workspace.frame(maxWidth: .infinity,maxHeight: .infinity); Divider(); inspector.frame(width: 286) }
                Divider()
                HStack { if store.busy { ProgressView().controlSize(.mini) }; Text(store.status).lineLimit(1); Spacer(); Text("SwiftUI · 本地运行") }.font(.system(size: 10)).foregroundStyle(.secondary).padding(.horizontal,14).frame(height: 27)
            }
        }.background(.white).foregroundStyle(ink).preferredColorScheme(.light).frame(minWidth: 1120,minHeight: 760)
        .alert("操作未完成",isPresented: Binding(get: { store.error != nil },set: { if !$0 { store.error = nil } })) { Button("好",role: .cancel) { store.error = nil } } message: { Text(store.error ?? "") }
        .sheet(isPresented: $store.diagnosticsVisible) { diagnostics }
    }
    private var sidebar: some View {
        VStack(alignment: .leading,spacing: 10) {
            HStack(spacing: 9) { Image(nsImage: NSApplication.shared.applicationIconImage).resizable().frame(width: 34,height: 34); Text("Ceda").font(.system(size: 21,weight: .semibold)); Text("Native").font(.system(size: 10)).foregroundStyle(.tertiary) }.padding(.bottom,18)
            Button(action: store.chooseBoard) { Label("导入 PCB",systemImage: "plus").frame(maxWidth: .infinity) }.controlSize(.large).disabled(store.busy)
            Text("工作空间").font(.system(size: 10)).foregroundStyle(.tertiary).padding(.top,24).padding(.bottom,3)
            ForEach(WorkspacePage.allCases,id: \.self) { page in
                Button { store.navigate(page) } label: {
                    Label(page.rawValue,systemImage: page.icon).font(.system(size: 12,weight: store.page == page ? .medium : .regular)).frame(maxWidth: .infinity,alignment: .leading).padding(.horizontal,10).padding(.vertical,10)
                        .foregroundStyle(store.page == page ? ink : .secondary).background(store.page == page ? Color.black.opacity(0.055) : .clear,in: RoundedRectangle(cornerRadius: 6))
                }.buttonStyle(.plain)
            }
            Text("项目").font(.system(size: 10)).foregroundStyle(.tertiary).padding(.top,25)
            if store.document != nil { Text(store.filename).font(.system(size: 11)).foregroundStyle(.secondary).lineLimit(2).padding(.leading,9) }
            Button("打开合成演示板",action: store.demo).font(.system(size: 11)).buttonStyle(.borderless).disabled(store.busy)
            Spacer()
            Text("本地工作空间\n数据与计算保留在本机").font(.system(size: 10)).foregroundStyle(.tertiary).lineSpacing(6)
        }.padding(.horizontal,15).padding(.top,27).padding(.bottom,18).frame(maxHeight: .infinity).background(Color(white: 0.975))
    }
    private var header: some View {
        HStack(spacing: 10) { Text("项目  /  \(store.filename)").font(.system(size: 11)).foregroundStyle(.secondary).lineLimit(1); Spacer()
            Button("打开工况",action: store.openConfig).buttonStyle(.borderless).disabled(store.busy || store.document == nil)
            Button("保存工况",action: store.saveConfig).disabled(store.busy || store.document == nil)
            Button(action: store.exportReport) { Label("导出报告",systemImage: "square.and.arrow.down") }.buttonStyle(.borderedProminent).tint(ink).disabled(store.result == nil || store.busy)
        }.controlSize(.regular).padding(.horizontal,24).frame(height: 52)
    }
    private var workspace: some View {
        VStack(alignment: .leading,spacing: 0) {
            HStack(alignment: .top) { VStack(alignment: .leading,spacing: 8) {
                Text(store.page == .models ? "板卡与器件模型" : store.page == .materials ? "叠层与材料" : "PCB 工作台").font(.system(size: 24,weight: .semibold))
                if let board = store.document?.board { Text("\(store.filename)  ·  \(board.layers.count) 铜层  ·  \(board.components.count) 器件  ·  \(board.pad_count) 焊盘").font(.system(size: 11,design: .monospaced)).foregroundStyle(.secondary) }
                else { Text("KiCad 后布局检查与规定工况仿真").font(.system(size: 11)).foregroundStyle(.secondary) }
            }; Spacer(); Text(store.verdict).font(.system(size: 11)).foregroundStyle(store.blocked || store.result?.verdict == "fail" ? .orange : .secondary).padding(.top,5) }.padding(.bottom,23)
            Divider()
            HStack(spacing: 12) {
                Picker("显示场",selection: $store.field) { ForEach(ViewField.allCases) { Text($0.rawValue).tag($0) } }.pickerStyle(.segmented).frame(maxWidth: 300).disabled(store.is3D)
                Spacer(minLength: 4)
                Picker("维度",selection: $store.is3D) { Text("二维").tag(false); Text("三维").tag(true) }.labelsHidden().frame(width: 82).onChange(of: store.is3D) { _,value in if value { store.buildMesh() } }
                Picker("活动铜层",selection: $store.layer) { ForEach(store.document?.board.layers.map(\.name) ?? ["F.Cu"],id: \.self) { Text($0).tag($0) } }.labelsHidden().frame(width: 90).disabled(store.is3D)
                Button(action: store.fit) { Image(systemName: "arrow.up.left.and.arrow.down.right") }.buttonStyle(.borderless).help("适应画布").accessibilityLabel("适应画布")
            }.padding(.vertical,12)
            Divider()
            VStack(spacing: 0) {
                HStack(spacing: 10) {
                    Menu { layerMenu } label: { Label("图层与显示",systemImage: "square.3.layers.3d") }.frame(width: 112)
                    if !store.is3D { Toggle("浅色",isOn: $store.lightCanvas).toggleStyle(.checkbox).font(.system(size: 10)) }
                    Spacer(minLength: 2)
                    ForEach([("俯视","top"),("背面","bottom"),("等轴","iso")],id: \.0) { title,pose in Button(title) { store.pose(pose) }.buttonStyle(.borderless).font(.system(size: 11)) }
                    Button("模型目录",action: store.chooseLibrary).buttonStyle(.borderless).font(.system(size: 11)).disabled(store.busy)
                    Button { store.diagnosticsVisible = true } label: { Image(systemName: "info.circle") }.buttonStyle(.borderless).help("模型与几何诊断")
                }.padding(10)
                if store.is3D { PCB3DView(store: store) } else { PCB2DView(store: store) }
            }.background(.white).clipShape(RoundedRectangle(cornerRadius: 6)).overlay(RoundedRectangle(cornerRadius: 6).stroke(Color.black.opacity(0.1))).padding(.top,16)
            HStack { Text(store.fieldLegend); Spacer(); Text(store.is3D ? "拖动旋转 · Shift 拖动平移 · 滚轮缩放" : store.cursor) }.font(.system(size: 10)).foregroundStyle(.tertiary).padding(.vertical,12)
            Divider()
            HStack { Text("负载端供电").font(.system(size: 12,weight: .semibold)); Spacer(); Button("查看完整报告 ↗",action: store.openReport).buttonStyle(.borderless).font(.system(size: 11)).disabled(store.result == nil) }.padding(.top,16).padding(.bottom,14)
            HStack { Text("负载 / 引脚").frame(maxWidth: .infinity,alignment: .leading); Text("本地 VDD–GND").frame(maxWidth: .infinity); Text("最低电压 / V").frame(maxWidth: .infinity); Text("判定").frame(maxWidth: .infinity) }.font(.system(size: 10)).foregroundStyle(.tertiary).padding(.bottom,10)
            Divider()
            ScrollView { VStack(spacing: 12) { ForEach(Array((store.result?.loads ?? []).enumerated()),id: \.offset) { _,load in
                HStack { Text(load.positive).frame(maxWidth: .infinity,alignment: .leading); Text(String(format: "%.6f V",load.voltage_v)).monospacedDigit().frame(maxWidth: .infinity); Text(load.minimum_voltage_v.map { String(format: "%.4f",$0) } ?? "未设定").frame(maxWidth: .infinity); Text(load.verdict == "fail" ? "低于设定值" : load.verdict == "pass" ? "当前工况通过" : "待验证").frame(maxWidth: .infinity) }.font(.system(size: 11))
            } }.padding(.top,10) }.frame(height: 66)
        }.padding(.horizontal,26).padding(.top,26).padding(.bottom,16)
    }
    @ViewBuilder private var layerMenu: some View {
        if store.is3D {
            ForEach(Array(["板体","铜层","阻焊","焊盘","丝印","器件"].enumerated()),id: \.offset) { index,title in Toggle(title,isOn: Binding(get: { store.categories.contains(index) },set: { if $0 { store.categories.insert(index) } else { store.categories.remove(index) } })) }
        } else {
            ForEach((store.document?.board.layers.map(\.name) ?? ["F.Cu","B.Cu"]) + ["F.SilkS","B.SilkS","F.Fab","B.Fab","F.CrtYd","B.CrtYd","Edge.Cuts"],id: \.self) { name in Toggle(name,isOn: Binding(get: { store.visibleLayers.contains(name) },set: { if $0 { store.visibleLayers.insert(name) } else { store.visibleLayers.remove(name) } })) }
            Divider(); Toggle("网格",isOn: $store.showGrid); Toggle("位号与引脚",isOn: $store.showLabels); Toggle("求解网格",isOn: $store.showMesh)
        }
    }
    private var inspector: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading,spacing: 15) {
                    HStack { Text(store.page == .models ? "模型与对象" : "分析工况").font(.system(size: 13,weight: .semibold)); Spacer(); Text("DC / 稳态").font(.system(size: 10)).foregroundStyle(.tertiary) }
                    if store.page == .models {
                        Text("按设计文件的模型路径与变换读取实际几何。缺失模型保留为空。").font(.system(size: 11)).foregroundStyle(.secondary)
                        if let mesh = store.mesh { Text("模型引用 \(mesh.models_loaded) / \(mesh.models_total)").font(.system(size: 12,weight: .medium)) }
                        Button("查看模型诊断") { store.diagnosticsVisible = true }
                        Divider()
                    }
                    if store.page == .materials, let board = store.document?.board {
                        ForEach(board.layers,id: \.name) { layer in HStack { Text(layer.name); Spacer(); Text(layer.thickness_mm.map { "\($0.formatted()) mm" } ?? "铜厚待提供") }.font(.system(size: 11)) }; Divider()
                    }
                    section("电源端口"); padPicker("正极焊盘",$store.sourceP); padPicker("回流焊盘",$store.sourceN); numeric("电压 / V",$store.voltage)
                    Divider().padding(.vertical,3)
                    section("负载端口"); padPicker("VDD 焊盘",$store.loadP); padPicker("本地 GND",$store.loadN); numeric("电流 / A",$store.current); numeric("最低电压 / V",$store.minimum)
                    VStack(spacing: 8) { ForEach(Array(store.loads.enumerated()),id: \.offset) { index,load in HStack { Text("\(load.positive) → \(load.negative)").lineLimit(1); Spacer(); Text("\(load.current_a.formatted()) A"); Button { store.loads.remove(at: index) } label: { Image(systemName: "minus.circle") }.buttonStyle(.borderless) }.font(.system(size: 10)) } }.padding(.vertical,4)
                    Button { store.addLoad() } label: { Label("添加负载",systemImage: "plus") }.buttonStyle(.borderless).font(.system(size: 11)).disabled(store.document == nil || store.busy)
                    Divider()
                    DisclosureGroup("网格与材料") { VStack(spacing: 12) { numeric("网格 / mm",$store.meshSize); numeric("铜厚 / mm",$store.copperThickness); numeric("孔镀层 / mm",$store.plating); Text("铜厚 0：使用文件叠层。\n孔镀层用于实际通孔电阻；不能从外观推断。\n其他参数保留导入工况的设置。").font(.system(size: 10)).foregroundStyle(.secondary) }.padding(.top,10) }.font(.system(size: 11))
                    Toggle("使用细化网格复核",isOn: $store.refine).toggleStyle(.checkbox).font(.system(size: 11))
                    Divider(); section("对象与计算质量")
                    if store.selectedPad != nil { Text(store.selectedDescription).font(.system(size: 11,design: .monospaced)).textSelection(.enabled) }
                    Text(store.diagnosticLines.prefix(4).joined(separator: "\n\n")).font(.system(size: 10)).foregroundStyle(.secondary).textSelection(.enabled)
                    Button("完整诊断与未验证项") { store.diagnosticsVisible = true }.buttonStyle(.borderless).font(.system(size: 11))
                }.padding(20).disabled(store.busy)
            }
            Divider()
            VStack(alignment: .leading,spacing: 10) {
                HStack { Button(action: store.analyze) { Label("开始供电分析",systemImage: "play").frame(maxWidth: .infinity) }.buttonStyle(.borderedProminent).tint(ink).disabled(store.busy || store.document == nil || store.blocked)
                    Button("取消",action: store.cancel).buttonStyle(.borderless).disabled(!store.busy)
                }
                Text("规定工况 DC · 芯片功能与实测校准未验证").font(.system(size: 10)).foregroundStyle(.tertiary)
                Text(store.log.suffix(3).joined(separator: "\n")).font(.system(size: 9,design: .monospaced)).foregroundStyle(.secondary).lineLimit(4).frame(height: 43,alignment: .topLeading)
            }.padding(18)
        }.background(.white)
    }
    private func section(_ title: String) -> some View { Text(title).font(.system(size: 11,weight: .medium)).foregroundStyle(.secondary).padding(.top,6) }
    private func padPicker(_ title: String,_ value: Binding<String>) -> some View {
        HStack { Text(title).font(.system(size: 11)).frame(width: 76,alignment: .leading)
            Picker(title,selection: value) { if store.document == nil { Text("未导入").tag("") }; ForEach(Array((store.document?.board.pads ?? []).enumerated()),id: \.offset) { _,pad in Text("\(pad.id) · \(pad.net)").tag(pad.id) } }.labelsHidden().frame(maxWidth: .infinity)
        }
    }
    private func numeric(_ title: String,_ value: Binding<Double>) -> some View { HStack { Text(title).font(.system(size: 11)).frame(width: 76,alignment: .leading); TextField(title,value: value,format: .number.precision(.fractionLength(0...5))).labelsHidden().textFieldStyle(.roundedBorder).font(.system(size: 11)).monospacedDigit() } }
    private var diagnostics: some View {
        VStack(alignment: .leading,spacing: 18) { HStack { Text("模型与分析诊断").font(.title2); Spacer(); Button("完成") { store.diagnosticsVisible = false }.keyboardShortcut(.defaultAction) }
            Text(store.filename).font(.system(.caption,design: .monospaced)).foregroundStyle(.secondary)
            ScrollView { VStack(alignment: .leading,spacing: 12) { ForEach(Array(store.diagnosticLines.enumerated()),id: \.offset) { _,line in Text(line).textSelection(.enabled) }
                Divider(); Text("三维用于几何检查，未叠加电磁场或温度结果。阻焊和金属在未指定外观时使用显示预设；丝印字体近似。未实现盲埋孔完整腔体和制造公差测量。").foregroundStyle(.secondary)
            }.font(.system(size: 12)).frame(maxWidth: .infinity,alignment: .leading) }
        }.padding(24).frame(width: 650,height: 500)
    }
}
