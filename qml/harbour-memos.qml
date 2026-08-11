import QtQuick 2.0
import Sailfish.Silica 1.0
import "pages"

ApplicationWindow {
    id: appWindow
    initialPage: Component { FirstPage { } }
    cover: Qt.resolvedUrl("cover/CoverPage.qml")

    allowedOrientations: defaultAllowedOrientations

    // LISÄÄ NÄMÄ:
    // Tämä pitää sisällään kansilehdellä näytettävän tekstin
    property string latestMemoText: "Haetaan..."
    property var py // Lisää tämä jotta MemoPage löytää Python-instanssin

    // Tämä signaali liipaistaan kansilehden napista
    signal requestNewMemo()
}
