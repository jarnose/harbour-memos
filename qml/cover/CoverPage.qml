import QtQuick 2.0
import Sailfish.Silica 1.0

CoverBackground {

    function formatCoverText(rawText) {
        if (!rawText) return "";
        var html = rawText;

        html = html.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '[Image: $1]');
        html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '$1');

        html = html.replace(/^###\s+(.*)$/gm, '<h3>$1</h3>');
        html = html.replace(/^##\s+(.*)$/gm, '<h2>$1</h2>');
        html = html.replace(/^#\s+(.*)$/gm, '<h1>$1</h1>');

        html = html.replace(/\*\*([^\*]+)\*\*/g, '<b>$1</b>');
        html = html.replace(/(^|[^\w\*])\*([^\*]+)\*(?=[^\w\*]|$)/g, '$1<i>$2</i>');
        html = html.replace(/(^|\s)(#[^\s]+)/g, '$1<font color="' + Theme.highlightColor + '">$2</font>');

        html = html.replace(/\n/g, '<br>');
        html = html.replace(/<\/h([1-3])><br>/g, '</h$1>');

        html = html.replace(/(^|<br>)([-*]\s+)?\[ \]\s/g, '$1<font color="#888888">☐</font> ');
        html = html.replace(/(^|<br>)([-*]\s+)?\[x\]\s/gi, '$1<font color="' + Theme.highlightColor + '">☑</font> ');

        return html;
    }

    Label {
        id: headerLabel
        anchors {
            top: parent.top
            topMargin: Theme.paddingLarge
            horizontalCenter: parent.horizontalCenter
        }
        text: "Memos"
        color: Theme.secondaryColor
        font.pixelSize: Theme.fontSizeSmall
    }

    Label {
        id: memoText
        anchors {
            top: headerLabel.bottom
            topMargin: Theme.paddingMedium
            left: parent.left
            right: parent.right
            leftMargin: Theme.paddingMedium
            rightMargin: Theme.paddingMedium
        }

        textFormat: Text.StyledText
        text: formatCoverText(appWindow.latestMemoText)

        color: Theme.primaryColor
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.WordWrap
        font.pixelSize: Theme.fontSizeMedium

        maximumLineCount: 7
        truncationMode: TruncationMode.Fade
    }

    CoverActionList {
        id: coverAction

        CoverAction {
            iconSource: "image://theme/icon-cover-new"
            onTriggered: {
                appWindow.activate()
                appWindow.requestNewMemo()
            }
        }
    }
}
