import Foundation

public struct PolygonData: Codable, Sendable { public var rings: [[[Double]]] }
public struct BoardIssue: Codable, Sendable { public var code: String; public var severity: String; public var message: String }
public struct CopperLayer: Codable, Sendable { public var name: String; public var thickness_mm: Double?; public var z_mm: Double? }
public struct PadInfo: Codable, Identifiable, Sendable {
    public var id: String; public var net: String; public var layers: [String]; public var x_mm: Double; public var y_mm: Double
}
public struct ComponentInfo: Codable, Sendable { public var value: String; public var footprint: String }
public struct BoardSummary: Codable, Sendable {
    public var path: String; public var sha256: String; public var layers: [CopperLayer]; public var pads: [PadInfo]
    public var pad_count: Int; public var via_count: Int; public var components: [String: ComponentInfo]
    public var board_thickness_mm: Double?; public var issues: [BoardIssue]
}
public struct RenderObject: Codable, Identifiable, Sendable {
    public var id: Int; public var kind: String; public var polygons: [PolygonData]; public var layer: String
    public var layers: [String]; public var net: String; public var pad_id: String?
}
public struct BoardText: Codable, Sendable {
    public var text: String; public var x: Double; public var y: Double; public var angle: Double
    public var layer: String; public var size: [Double]; public var mirror: Bool
}
public struct BoardDocument: Codable, Sendable {
    public var schema_version: Int; public var board: BoardSummary; public var bounds_mm: [Double]?
    public var outline: [PolygonData]; public var objects: [RenderObject]; public var texts: [BoardText]; public var warnings: [String]
    public static func read(_ url: URL) throws -> Self {
        let value = try JSONDecoder().decode(Self.self, from: Data(contentsOf: url))
        guard value.schema_version == 1, let b = value.bounds_mm, b.count == 4, b.allSatisfy(\.isFinite), b[2] > b[0], b[3] > b[1] else {
            throw ContractError.invalid("PCB 显示协议或边界无效")
        }
        for object in value.objects {
            for polygon in object.polygons {
                guard polygon.rings.allSatisfy({ $0.count >= 3 && $0.allSatisfy({ $0.count == 2 && $0.allSatisfy(\.isFinite) }) }) else {
                    throw ContractError.invalid("PCB 多边形坐标无效")
                }
            }
        }
        return value
    }
}
public enum ContractError: LocalizedError {
    case invalid(String)
    public var errorDescription: String? { if case let .invalid(s) = self { return s }; return nil }
}
public struct MeshDocument: Codable, Sendable {
    public var schema_version: Int; public var vertices_file: String; public var vertex_count: Int; public var stride_bytes: Int
    public var center_mm: [Double]; public var span_mm: Double; public var categories: [String]
    public var models_loaded: Int; public var models_total: Int; public var warnings: [String]; public var board_sha256: String
    public static func read(_ directory: URL, boardHash: String) throws -> (Self, Data) {
        let value = try JSONDecoder().decode(Self.self, from: Data(contentsOf: directory.appendingPathComponent("mesh.json")))
        guard value.schema_version == 1, value.stride_bytes == 40, value.vertex_count > 0, value.vertex_count <= 12_000_000,
              value.vertex_count % 3 == 0, value.span_mm.isFinite, value.span_mm > 0,
              value.vertices_file == "vertices.bin", value.board_sha256 == boardHash else { throw ContractError.invalid("三维数据协议或板卡快照不匹配") }
        let data = try Data(contentsOf: directory.appendingPathComponent(value.vertices_file))
        guard data.count == value.vertex_count * value.stride_bytes else { throw ContractError.invalid("三维顶点文件长度不完整") }
        let valid = data.withUnsafeBytes { raw in raw.bindMemory(to: Float.self).allSatisfy(\.isFinite) }
        guard valid else { throw ContractError.invalid("三维顶点包含无效数值") }
        return (value, data)
    }
}
public struct LoadResult: Codable, Identifiable, Sendable {
    public var positive: String; public var negative: String; public var voltage_v: Double; public var minimum_voltage_v: Double?; public var verdict: String
    public var id: String { positive + "|" + negative }
}
public struct FieldMesh: Codable, Sendable {
    public var points_mm: [[Double]]; public var triangles: [[Int]]; public var triangle_keys: [[String]]
    public var voltage_v: [Double]; public var current_density_a_mm2: [Double]
}
public struct AnalysisResult: Codable, Sendable {
    public var verdict: String; public var loads: [LoadResult]; public var mesh: FieldMesh; public var unverified: [String]
}
public enum ViewField: String, CaseIterable, Identifiable {
    case geometry = "板卡几何", current = "电流密度", voltage = "电压分布"
    public var id: String { rawValue }
}
public struct ViewportTransform: Sendable {
    public var scale: Double; public var offsetX: Double; public var offsetY: Double
    public init(bounds: [Double], width: Double, height: Double, zoom: Double, panX: Double, panY: Double) {
        scale = max(0.01, min((width - 50) / (bounds[2] - bounds[0]), (height - 50) / (bounds[3] - bounds[1]))) * zoom
        offsetX = width / 2 - (bounds[0] + bounds[2]) / 2 * scale + panX
        offsetY = height / 2 - (bounds[1] + bounds[3]) / 2 * scale + panY
    }
    public func screen(_ point: [Double]) -> (Double, Double) { (point[0] * scale + offsetX, point[1] * scale + offsetY) }
    public func board(x: Double, y: Double) -> (Double, Double) { ((x - offsetX) / scale, (y - offsetY) / scale) }
}
