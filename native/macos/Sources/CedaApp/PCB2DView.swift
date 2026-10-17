import SwiftUI
import AppKit
import CedaCore

private let layerColors: [String: Color] = ["F.Cu": Color(red: 0.86, green: 0.37, blue: 0.37),"B.Cu": Color(red: 0.35, green: 0.59, blue: 0.88),"F.SilkS": Color(red: 0.95, green: 0.94, blue: 0.83),"B.SilkS": .cyan,"F.Fab": .gray,"B.Fab": .gray,"F.CrtYd": .purple,"B.CrtYd": .purple]
func fieldColor(_ value: Double, _ low: Double, _ high: Double) -> Color {
    let t = max(0,min(1,(value-low)/max(high-low,1e-20)))
    let stops: [[Double]] = [[232,237,243],[161,183,212],[90,136,185],[239,182,132],[212,107,85]]
    let index = min(Int(t*4),3); let f = t*4-Double(index); let a = stops[index], b = stops[index+1]
    return Color(red: (a[0]+(b[0]-a[0])*f)/255,green: (a[1]+(b[1]-a[1])*f)/255,blue: (a[2]+(b[2]-a[2])*f)/255)
}
func polygonPath(_ polygons: [PolygonData]) -> Path {
    Path { path in
        for polygon in polygons { for ring in polygon.rings {
            guard let first = ring.first else { continue }; path.move(to: CGPoint(x: first[0],y: first[1]))
            for point in ring.dropFirst() { path.addLine(to: CGPoint(x: point[0],y: point[1])) }; path.closeSubpath()
        } }
    }
}
struct PCB2DView: View {
    @ObservedObject var store: WorkbenchStore
    @State private var paths: [Int: Path] = [:]; @State private var outline = Path()
    var body: some View {
        GeometryReader { geometry in
            ZStack {
                Canvas(opaque: true, rendersAsynchronously: true) { context,size in
                    context.fill(Path(CGRect(origin: .zero,size: size)), with: .color(store.lightCanvas ? Color(white: 0.98) : Color(red: 0.085,green: 0.115,blue: 0.15)))
                    guard let document = store.document, let bounds = document.bounds_mm else { return }
                    let transform = mapping(bounds,size)
                    if store.showGrid { drawGrid(&context,size,transform) }
                    var boardContext = context
                    boardContext.translateBy(x: transform.offsetX,y: transform.offsetY); boardContext.scaleBy(x: transform.scale,y: transform.scale)
                    boardContext.fill(outline,with: .color(store.lightCanvas ? Color(white: 0.94) : Color(red: 0.12,green: 0.17,blue: 0.20)),style: FillStyle(eoFill: true))
                    let ordered = document.objects.sorted { priority($0) < priority($1) }
                    for object in ordered where visible(object) {
                        guard let path = paths[object.id] else { continue }
                        var paint = boardContext
                        switch object.kind {
                        case "copper": paint.opacity = object.layer == store.layer ? 0.50 : 0.16
                        case "track": paint.opacity = object.layer == store.layer ? 1 : 0.28
                        default: break
                        }
                        paint.fill(path,with: .color(objectColor(object)),style: FillStyle(eoFill: true))
                    }
                    if let mesh = store.result?.mesh, store.field != .geometry { drawField(&boardContext,mesh) }
                    if store.visibleLayers.contains("Edge.Cuts") { boardContext.stroke(outline,with: .color(store.lightCanvas ? Color.brown : Color(red: 0.86,green: 0.82,blue: 0.47)),lineWidth: 0.06) }
                    if let selected = store.selectedPad {
                        for object in document.objects where object.pad_id == selected && object.layers.contains(store.layer) {
                            if let path = paths[object.id] { boardContext.stroke(path,with: .color(.cyan),lineWidth: 0.10) }
                        }
                    }
                    if store.showLabels { drawLabels(&context,document,transform) }
                    drawScale(&context,size,transform.scale)
                }
                ViewportInput(onDrag: { delta,_ in store.pan2D.width += delta.width; store.pan2D.height += delta.height },
                    onScroll: { point,dy in zoom(point,dy,geometry.size) },
                    onClick: { point in pick(point,geometry.size) }, onMove: { point in
                        guard let b = store.document?.bounds_mm else { return }; let p = mapping(b,geometry.size).board(x: point.x,y: point.y)
                        store.cursor = String(format: "X %.3f  Y %.3f mm",p.0,p.1)
                    })
                if store.document == nil {
                    VStack(spacing: 14) { Image(systemName: "cpu").font(.system(size: 34,weight: .ultraLight)); Text("导入真实 PCB").font(.title3); Text("板框、铜层、焊盘与模型均来自设计文件").font(.caption)
                        Button("导入 KiCad PCB",action: store.chooseBoard).buttonStyle(.borderedProminent)
                        Button("打开合成演示板",action: store.demo).buttonStyle(.borderless)
                    }.foregroundStyle(store.lightCanvas ? .secondary : Color(white: 0.7))
                }
            }.clipped()
        }.onAppear(perform: prepare).onChange(of: store.document?.board.sha256) { _,_ in prepare() }
    }
    private func prepare() { paths = Dictionary(uniqueKeysWithValues: (store.document?.objects ?? []).map { ($0.id,polygonPath($0.polygons)) }); outline = polygonPath(store.document?.outline ?? []) }
    private func mapping(_ b: [Double], _ s: CGSize) -> ViewportTransform { ViewportTransform(bounds: b,width: s.width,height: s.height,zoom: store.zoom2D,panX: store.pan2D.width,panY: store.pan2D.height) }
    private func visible(_ object: RenderObject) -> Bool {
        if ["pad","via","hole"].contains(object.kind) { return object.layers.contains(store.layer) }
        if object.layer.hasSuffix(".Cu") { return object.layer == store.layer || store.visibleLayers.contains(object.layer) }
        let front = store.layer != "B.Cu"
        return store.visibleLayers.contains(object.layer) && !(front && object.layer.hasPrefix("B.")) && !(!front && object.layer.hasPrefix("F."))
    }
    private func priority(_ object: RenderObject) -> Int { switch object.kind { case "copper": return object.layer == store.layer ? 2 : 1; case "track": return 3; case "graphic": return 4; case "pad": return 5; case "via": return 6; case "hole": return 7; default: return 0 } }
    private func objectColor(_ object: RenderObject) -> Color {
        switch object.kind {
        case "pad","via": return Color(red: 0.86,green: 0.71,blue: 0.48)
        case "hole": return store.lightCanvas ? .white : Color(red: 0.05,green: 0.075,blue: 0.10)
        default: if store.lightCanvas && object.layer.hasSuffix("SilkS") { return Color(red: 0.29,green: 0.38,blue: 0.27) }; return layerColors[object.layer] ?? .gray
        }
    }
    private func drawGrid(_ context: inout GraphicsContext,_ size: CGSize,_ transform: ViewportTransform) {
        var step = 0.5; while step * transform.scale < 16 { step *= 2 }
        let origin = transform.board(x: 0,y: 0); let end = transform.board(x: size.width,y: size.height)
        var path = Path(); var x = floor(origin.0/step)*step
        while x < end.0 { var y = floor(origin.1/step)*step
            while y < end.1 { let p = transform.screen([x,y]); path.addEllipse(in: CGRect(x: p.0,y: p.1,width: 0.8,height: 0.8)); y += step }; x += step }
        context.fill(path,with: .color(store.lightCanvas ? Color(white: 0.8) : Color(white: 0.25)))
    }
    private func drawLabels(_ context: inout GraphicsContext,_ document: BoardDocument,_ transform: ViewportTransform) {
        for label in document.texts where store.visibleLayers.contains(label.layer) {
            if label.layer.hasPrefix("B.") != (store.layer == "B.Cu") { continue }
            let height = label.size[1]*transform.scale; if height < 7 { continue }
            var paint = context; let p = transform.screen([label.x,label.y]); paint.translateBy(x: p.0,y: p.1); paint.rotate(by: .degrees(-label.angle)); if label.mirror { paint.scaleBy(x: -1,y: 1) }
            paint.draw(Text(label.text).font(.system(size: height)).foregroundColor(store.lightCanvas ? .secondary : Color(red: 0.93,green: 0.92,blue: 0.82)),at: .zero)
        }
        for pad in document.board.pads where pad.layers.contains(store.layer) {
            let p = transform.screen([pad.x_mm,pad.y_mm]); let number = pad.id.split(separator: ".").last.map(String.init) ?? ""
            let object = document.objects.first { $0.pad_id == pad.id }
            let ring = object?.polygons.first?.rings.first ?? []
            let height = ((ring.map { $0[1] }.max() ?? pad.y_mm) - (ring.map { $0[1] }.min() ?? pad.y_mm))*transform.scale*0.38
            if height >= 7 { context.draw(Text(number).font(.system(size: min(13,height),weight: .medium)).foregroundColor(.black.opacity(0.75)),at: CGPoint(x: p.0,y: p.1)) }
        }
    }
    private func drawScale(_ context: inout GraphicsContext,_ size: CGSize,_ scale: Double) {
        var length = pow(10,floor(log10(90/max(scale,1e-9)))); if length*scale < 40 { length *= 5 }
        let y = size.height-24; var p = Path(); p.move(to: CGPoint(x: 22,y: y)); p.addLine(to: CGPoint(x: 22+length*scale,y: y))
        context.stroke(p,with: .color(.gray),lineWidth: 1); context.draw(Text("\(length.formatted()) mm").font(.system(size: 10)).foregroundColor(.gray),at: CGPoint(x: 22,y: y-12),anchor: .leading)
    }
    private func drawField(_ context: inout GraphicsContext,_ mesh: FieldMesh) {
        let indices = mesh.triangles.indices.filter { mesh.triangle_keys[$0][1] == store.layer }
        let values = mesh.triangles.indices.map { i -> Double in store.field == .current ? mesh.current_density_a_mm2[i] : mesh.triangles[i].map { mesh.voltage_v[$0] }.reduce(0,+)/3 }
        guard let lo = indices.map({ values[$0] }).min(), let hi = indices.map({ values[$0] }).max() else { return }
        for i in indices { let points = mesh.triangles[i].map { mesh.points_mm[$0] }; var p = Path(); p.move(to: CGPoint(x: points[0][0],y: points[0][1])); for point in points.dropFirst() { p.addLine(to: CGPoint(x: point[0],y: point[1])) }; p.closeSubpath()
            context.fill(p,with: .color(fieldColor(values[i],lo,hi))); if store.showMesh { context.stroke(p,with: .color(.gray.opacity(0.5)),lineWidth: 0.008) }
        }
    }
    private func zoom(_ point: CGPoint,_ delta: CGFloat,_ size: CGSize) {
        guard let bounds = store.document?.bounds_mm else { return }; let world = mapping(bounds,size).board(x: point.x,y: point.y)
        store.zoom2D = min(80,max(0.08,store.zoom2D*exp(delta*0.012)))
        let next = mapping(bounds,size).screen([world.0,world.1]); store.pan2D.width += point.x-next.0; store.pan2D.height += point.y-next.1
    }
    private func pick(_ point: CGPoint,_ size: CGSize) {
        guard let document = store.document, let b = document.bounds_mm else { return }; let value = mapping(b,size).board(x: point.x,y: point.y)
        let p = CGPoint(x: value.0,y: value.1)
        if let object = document.objects.reversed().first(where: { $0.kind == "pad" && $0.layers.contains(store.layer) && (paths[$0.id]?.contains(p,eoFill: true) ?? false) }), let id = object.pad_id { store.selectPad(id) }
    }
}
struct ViewportInput: NSViewRepresentable {
    var onDrag: (CGSize,Bool) -> Void; var onScroll: (CGPoint,CGFloat) -> Void; var onClick: (CGPoint) -> Void; var onMove: (CGPoint) -> Void
    func makeNSView(context: Context) -> InputView { let view = InputView(); updateNSView(view,context: context); return view }
    func updateNSView(_ view: InputView,context: Context) { view.drag = onDrag; view.scroll = onScroll; view.click = onClick; view.move = onMove }
}
final class InputView: NSView {
    var drag: ((CGSize,Bool) -> Void)?; var scroll: ((CGPoint,CGFloat) -> Void)?; var click: ((CGPoint) -> Void)?; var move: ((CGPoint) -> Void)?
    private var distance: CGFloat = 0
    override var isFlipped: Bool { true }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
    override func updateTrackingAreas() { super.updateTrackingAreas(); trackingAreas.forEach(removeTrackingArea); addTrackingArea(NSTrackingArea(rect: bounds,options: [.mouseMoved,.activeInKeyWindow,.inVisibleRect],owner: self)) }
    override func mouseDown(with event: NSEvent) { distance = 0 }
    override func mouseDragged(with event: NSEvent) { distance += abs(event.deltaX)+abs(event.deltaY); drag?(CGSize(width: event.deltaX,height: event.deltaY),event.modifierFlags.contains(.shift)) }
    override func rightMouseDragged(with event: NSEvent) { drag?(CGSize(width: event.deltaX,height: event.deltaY),true) }
    override func mouseUp(with event: NSEvent) { if distance < 4 { click?(convert(event.locationInWindow,from: nil)) } }
    override func mouseMoved(with event: NSEvent) { move?(convert(event.locationInWindow,from: nil)) }
    override func scrollWheel(with event: NSEvent) { scroll?(convert(event.locationInWindow,from: nil),event.scrollingDeltaY) }
}
