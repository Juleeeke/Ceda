import QtQuick
import QtQuick3D
Rectangle {
    color: "#eef1f2"
    View3D {
        anchors.fill: parent
        environment: SceneEnvironment {
            backgroundMode: SceneEnvironment.Color
            clearColor: "#eef1f2"
            antialiasingMode: SceneEnvironment.MSAA
            antialiasingQuality: SceneEnvironment.High
            tonemapMode: SceneEnvironment.TonemapModeLinear
            aoStrength: 35
            aoDistance: 1.2
            aoSampleRate: 4
        }
        OrthographicCamera {
            z: 1000
            clipNear: 0.1
            clipFar: 3000
            horizontalMagnification: boardScene.magnification
            verticalMagnification: boardScene.magnification
        }
        DirectionalLight {
            eulerRotation: Qt.vector3d(-25, -30, 0)
            brightness: 0.9
            ambientColor: "#777777"
            castsShadow: true
            shadowMapQuality: Light.ShadowMapQualityHigh
            shadowBias: 0.01
        }
        DirectionalLight { eulerRotation: Qt.vector3d(50, 100, 20); brightness: 0.35 }
        Node {
            rotation: boardScene.orientation
            position: boardScene.pan
            Repeater3D {
                model: boardScene.parts
                delegate: Model {
                    required property var modelData
                    geometry: modelData.geometry
                    visible: boardScene.enabled.indexOf(modelData.category) >= 0
                    castsShadows: modelData.category === "models"
                    receivesShadows: true
                    materials: PrincipledMaterial {
                        baseColor: modelData.color
                        metalness: (modelData.category === "pads" || modelData.category === "copper") ? 0.55 : 0.0
                        roughness: modelData.category === "mask" ? 0.42 : 0.65
                        cullMode: Material.NoCulling
                    }
                }
            }
        }
    }
}
