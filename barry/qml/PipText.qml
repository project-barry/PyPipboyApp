// Text in the Pip-Boy's colour and font.
import QtQuick

Text {
    color: Pip.color
    font.family: Pip.font
    font.pixelSize: Pip.body
    elide: Text.ElideRight
    verticalAlignment: Text.AlignVCenter
}
