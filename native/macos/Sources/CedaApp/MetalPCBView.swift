import SwiftUI
import MetalKit
import simd
import CedaCore

private let shaderSource = """
#include <metal_stdlib>
using namespace metal;
struct Vertex { packed_float3 position; packed_float3 normal; packed_float3 color; float category; };
struct Uniforms { float4x4 mvp; float4x4 rotation; uint4 visibility; };
struct Output { float4 position [[position]]; float3 normal; float3 color; uint category [[flat]]; };
vertex Output pcb_vertex(uint id [[vertex_id]], const device Vertex *vertices [[buffer(0)]], constant Uniforms &u [[buffer(1)]]) {
    Vertex v = vertices[id]; Output o;
    o.position = u.mvp * float4(float3(v.position),1.0);
    o.normal = (u.rotation * float4(float3(v.normal),0.0)).xyz;
    o.color = float3(v.color); o.category = uint(v.category); return o;
}
fragment float4 pcb_fragment(Output v [[stage_in]], bool front [[front_facing]], constant Uniforms &u [[buffer(1)]]) {
    if ((u.visibility.x & (1u << v.category)) == 0) discard_fragment();
    float3 normal = normalize(v.normal) * (front ? 1.0 : -1.0);
    float3 light = normalize(float3(-0.3,0.5,0.82));
    float diffuse = max(dot(normal,light),0.0);
    float specular = pow(max(dot(normal,normalize(light+float3(0,0,1))),0.0),32.0);
    float metal = (v.category == 1 || v.category == 3) ? 0.12 : 0.015;
    return float4(clamp(v.color*(0.40+0.60*diffuse)+specular*metal,0.0,1.0),1.0);
}
"""
struct MetalUniforms {
    var mvp: simd_float4x4; var rotation: simd_float4x4; var visibility: SIMD4<UInt32>
}
func cameraUniforms(width: Float,height: Float,span: Float,yaw: Float,tilt: Float,zoom: Float,pan: CGSize,categories: Set<Int>) -> MetalUniforms {
    let rx = tilt * .pi/180, rz = yaw * .pi/180
    let x = simd_float4x4(SIMD4(1,0,0,0),SIMD4(0,cos(rx),sin(rx),0),SIMD4(0,-sin(rx),cos(rx),0),SIMD4(0,0,0,1))
    let z = simd_float4x4(SIMD4(cos(rz),sin(rz),0,0),SIMD4(-sin(rz),cos(rz),0,0),SIMD4(0,0,1,0),SIMD4(0,0,0,1))
    let rotation = x*z; let scale = min(width,height)*0.82/max(span,0.01)*zoom
    let projection = simd_float4x4(SIMD4(2*scale/max(width,1),0,0,0),SIMD4(0,2*scale/max(height,1),0,0),SIMD4(0,0,-1/max(span*4,1),0),SIMD4(2*Float(pan.width)/max(width,1),-2*Float(pan.height)/max(height,1),0.5,1))
    let mask = categories.reduce(UInt32(0)) { $0 | (UInt32(1) << UInt32($1)) }
    return MetalUniforms(mvp: projection*rotation,rotation: rotation,visibility: SIMD4(mask,0,0,0))
}
final class MetalRenderer: NSObject, MTKViewDelegate {
    let device: MTLDevice; let queue: MTLCommandQueue; private let pipeline: MTLRenderPipelineState; private let depth: MTLDepthStencilState
    private var buffer: MTLBuffer?; private var count = 0; private var dataIdentity: Int = 0
    var span: Float = 1; var yaw: Float = -65; var tilt: Float = 48; var zoom: Float = 1; var pan = CGSize.zero; var categories = Set(0..<6)
    init(device: MTLDevice) throws {
        self.device = device
        guard let queue = device.makeCommandQueue() else { throw ContractError.invalid("无法创建 Metal 命令队列") }; self.queue = queue
        let library = try device.makeLibrary(source: shaderSource,options: nil)
        let descriptor = MTLRenderPipelineDescriptor(); descriptor.vertexFunction = library.makeFunction(name: "pcb_vertex"); descriptor.fragmentFunction = library.makeFunction(name: "pcb_fragment")
        descriptor.colorAttachments[0].pixelFormat = .bgra8Unorm_srgb; descriptor.depthAttachmentPixelFormat = .depth32Float; descriptor.rasterSampleCount = 4
        pipeline = try device.makeRenderPipelineState(descriptor: descriptor)
        let depthDescriptor = MTLDepthStencilDescriptor(); depthDescriptor.depthCompareFunction = .lessEqual; depthDescriptor.isDepthWriteEnabled = true
        guard let depth = device.makeDepthStencilState(descriptor: depthDescriptor) else { throw ContractError.invalid("无法创建深度缓冲") }; self.depth = depth
        super.init()
    }
    func load(_ data: Data,count: Int) throws {
        guard data.count == count*40 else { throw ContractError.invalid("Metal 顶点布局不匹配") }
        buffer = data.withUnsafeBytes { raw in device.makeBuffer(bytes: raw.baseAddress!,length: data.count,options: .storageModeShared) }
        guard buffer != nil else { throw ContractError.invalid("无法为真实 PCB 网格分配显存") }; self.count = count
    }
    private func encode(_ command: MTLCommandBuffer,pass: MTLRenderPassDescriptor,size: CGSize) {
        guard let encoder = command.makeRenderCommandEncoder(descriptor: pass) else { return }; defer { encoder.endEncoding() }
        guard let buffer, count > 0 else { return }
        var uniforms = cameraUniforms(width: Float(size.width),height: Float(size.height),span: span,yaw: yaw,tilt: tilt,zoom: zoom,pan: pan,categories: categories)
        encoder.setRenderPipelineState(pipeline); encoder.setDepthStencilState(depth); encoder.setCullMode(.none)
        encoder.setVertexBuffer(buffer,offset: 0,index: 0); encoder.setVertexBytes(&uniforms,length: MemoryLayout<MetalUniforms>.stride,index: 1)
        encoder.setFragmentBytes(&uniforms,length: MemoryLayout<MetalUniforms>.stride,index: 1)
        encoder.drawPrimitives(type: .triangle,vertexStart: 0,vertexCount: count)
    }
    func mtkView(_ view: MTKView,drawableSizeWillChange size: CGSize) {}
    func draw(in view: MTKView) {
        guard let drawable = view.currentDrawable, let pass = view.currentRenderPassDescriptor, let command = queue.makeCommandBuffer() else { return }
        encode(command,pass: pass,size: view.bounds.size); command.present(drawable); command.commit()
    }
    func snapshot(width: Int,height: Int) throws -> Data {
        let finalDescriptor = MTLTextureDescriptor.texture2DDescriptor(pixelFormat: .bgra8Unorm_srgb,width: width,height: height,mipmapped: false)
        finalDescriptor.usage = [.renderTarget,.shaderRead]; finalDescriptor.storageMode = .shared
        let msaaDescriptor = MTLTextureDescriptor(); msaaDescriptor.textureType = .type2DMultisample; msaaDescriptor.pixelFormat = .bgra8Unorm_srgb
        msaaDescriptor.width = width; msaaDescriptor.height = height; msaaDescriptor.sampleCount = 4; msaaDescriptor.usage = .renderTarget; msaaDescriptor.storageMode = .private
        let depthDescriptor = msaaDescriptor.copy() as! MTLTextureDescriptor; depthDescriptor.pixelFormat = .depth32Float
        guard let texture = device.makeTexture(descriptor: finalDescriptor), let msaa = device.makeTexture(descriptor: msaaDescriptor), let depthTexture = device.makeTexture(descriptor: depthDescriptor), let command = queue.makeCommandBuffer() else { throw ContractError.invalid("无法创建 Metal 离屏渲染目标") }
        let pass = MTLRenderPassDescriptor(); pass.colorAttachments[0].texture = msaa; pass.colorAttachments[0].resolveTexture = texture
        pass.colorAttachments[0].loadAction = .clear; pass.colorAttachments[0].storeAction = .multisampleResolve; pass.colorAttachments[0].clearColor = MTLClearColorMake(0.93,0.945,0.95,1)
        pass.depthAttachment.texture = depthTexture; pass.depthAttachment.loadAction = .clear; pass.depthAttachment.storeAction = .dontCare; pass.depthAttachment.clearDepth = 1
        encode(command,pass: pass,size: CGSize(width: width,height: height)); command.commit(); command.waitUntilCompleted()
        if let error = command.error { throw error }
        var pixels = [UInt8](repeating: 0,count: width*height*4)
        texture.getBytes(&pixels,bytesPerRow: width*4,from: MTLRegionMake2D(0,0,width,height),mipmapLevel: 0)
        for i in stride(from: 0,to: pixels.count,by: 4) { pixels.swapAt(i,i+2) }
        guard let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil,pixelsWide: width,pixelsHigh: height,bitsPerSample: 8,samplesPerPixel: 4,hasAlpha: true,isPlanar: false,colorSpaceName: .deviceRGB,bytesPerRow: width*4,bitsPerPixel: 32), let destination = bitmap.bitmapData else { throw ContractError.invalid("无法创建渲染验证图片") }
        pixels.withUnsafeBytes { raw in destination.update(from: raw.bindMemory(to: UInt8.self).baseAddress!,count: pixels.count) }
        guard let png = bitmap.representation(using: .png,properties: [:]) else { throw ContractError.invalid("渲染验证图片编码失败") }; return png
    }
}
struct MetalPCBView: NSViewRepresentable {
    @ObservedObject var store: WorkbenchStore
    final class Coordinator {
        var renderer: MetalRenderer?; var loadedRevision: UUID?
    }
    func makeCoordinator() -> Coordinator { Coordinator() }
    func makeNSView(context: Context) -> MTKView {
        let view = MTKView(frame: .zero,device: MTLCreateSystemDefaultDevice()); view.sampleCount = 4; view.colorPixelFormat = .bgra8Unorm_srgb; view.depthStencilPixelFormat = .depth32Float
        view.clearColor = MTLClearColorMake(0.93,0.945,0.95,1); view.isPaused = true; view.enableSetNeedsDisplay = true
        do { guard let device = view.device else { throw ContractError.invalid("本机没有可用的 Metal 设备") }; let renderer = try MetalRenderer(device: device); context.coordinator.renderer = renderer; view.delegate = renderer }
        catch { Task { @MainActor in store.error = error.localizedDescription } }
        return view
    }
    func updateNSView(_ view: MTKView,context: Context) {
        guard let renderer = context.coordinator.renderer, let metadata = store.mesh, let bytes = store.vertices else { return }
        if context.coordinator.loadedRevision != store.meshRevision {
            do { try renderer.load(bytes,count: metadata.vertex_count); context.coordinator.loadedRevision = store.meshRevision }
            catch { Task { @MainActor in store.error = error.localizedDescription }; return }
        }
        renderer.span = Float(metadata.span_mm); renderer.yaw = store.yaw; renderer.tilt = store.tilt; renderer.zoom = store.zoom3D; renderer.pan = store.pan3D; renderer.categories = store.categories
        view.needsDisplay = true
    }
}
struct PCB3DView: View {
    @ObservedObject var store: WorkbenchStore
    var body: some View {
        ZStack {
            MetalPCBView(store: store)
            ViewportInput(onDrag: { delta,shift in
                if shift { store.pan3D.width += delta.width; store.pan3D.height += delta.height }
                else { store.yaw += Float(delta.width)*0.5; store.tilt = min(180,max(-180,store.tilt+Float(delta.height)*0.5)) }
            }, onScroll: { _,delta in store.zoom3D = min(20,max(0.1,store.zoom3D*exp(Float(delta)*0.012))) },onClick: { _ in },onMove: { _ in })
            VStack { HStack { Text("3D / Metal · 毫米坐标"); Spacer(); if let t = store.document?.board.board_thickness_mm { Text("板厚 \(t.formatted()) mm") } }; Spacer()
                HStack { if let mesh = store.mesh { Text("模型引用 \(mesh.models_loaded)/\(mesh.models_total) · \(mesh.warnings.count) 项提示") } else { Text(store.busy ? store.status : "需要闭合板框、有效板厚和实际模型文件") }; Spacer() }
            }.font(.system(size: 11)).foregroundStyle(.secondary).padding(16).allowsHitTesting(false)
            if store.busy && store.mesh == nil { ProgressView().controlSize(.small) }
        }.onAppear { store.buildMesh() }
    }
}
