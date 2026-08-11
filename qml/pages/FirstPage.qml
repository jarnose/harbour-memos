import QtQuick 2.0
import Sailfish.Silica 1.0
import io.thp.pyotherside 1.0

Page {
    id: page
    allowedOrientations: Orientation.All

    property string errorMessage: ""
    property int listLineCount: 2
    property int listCoverMode: 0 // UUSI: 0 = Luotu, 1 = Muokattu

    function formatText(rawText) {
        if (!rawText) return "";
        var html = rawText;

        html = html.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<a href="$2">[Kuva: $1]</a>');
        html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');
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

    Python {
        id: py
        Component.onCompleted: {
            appWindow.py = py;
            addImportPath(Qt.resolvedUrl('../../python'));
            importModule('memos', function() {
                py.call('memos.api.get_settings', [], function(settings) {
                    if (settings && settings.line_count !== undefined) {
                        page.listLineCount = settings.line_count;
                    }
                    if (settings && settings.cover_mode !== undefined) {
                        page.listCoverMode = settings.cover_mode;
                    }

                    py.call('memos.api.sync_queue', [], function() {
                        py.call('memos.api.fetch_memos', []);
                    });
                });
            });
        }

        onReceived: {
            if (data[0] === 'memos_fetched') {
                page.errorMessage = "";
                memoModel.clear();
                var memos = data[1];

                // --- KANSILEHDEN LOGIIKKA ---
                if (memos.length > 0) {
                    var latestContent = memos[0].content || memos[0].name;

                    if (page.listCoverMode === 1) {
                        // Etsitään muokkausajaltaan uusin
                        var maxMs = 0;
                        var maxIdx = 0;
                        for (var m = 0; m < memos.length; m++) {
                            if (memos[m].name === "queued") {
                                maxMs = Date.now(); // Jonossa oleva katsotaan aina tuoreimmaksi
                                maxIdx = m;
                            } else {
                                var parseTime = memos[m].updateTime || memos[m].updatedTs || memos[m].createTime || memos[m].createdTs || 0;
                                var uMs = typeof parseTime === "number" ? parseTime * 1000 : new Date(parseTime).getTime();
                                if (uMs > maxMs) {
                                    maxMs = uMs;
                                    maxIdx = m;
                                }
                            }
                        }
                        latestContent = memos[maxIdx].content || memos[maxIdx].name;
                    }
                    appWindow.latestMemoText = latestContent;
                } else {
                    appWindow.latestMemoText = "Ei merkintöjä";
                }

                // --- LISTAN JA AIKALEIMOJEN LOGIIKKA ---
                for (var i = 0; i < memos.length; i++) {
                    var mId = memos[i].name || memos[i].id || "unknown";
                    var timeStr = "";

                    if (mId !== "queued") {
                        // Parsitaan luontiaika
                        var cRaw = memos[i].createTime || memos[i].createdTs || "";
                        var cMs = typeof cRaw === "number" ? cRaw * 1000 : (cRaw ? new Date(cRaw).getTime() : 0);
                        var cStr = cMs > 0 ? Qt.formatDateTime(new Date(cMs), "d.M.yyyy hh:mm") : "";

                        // Parsitaan muokkausaika
                        var uRaw = memos[i].updateTime || memos[i].updatedTs || "";
                        var uMs = typeof uRaw === "number" ? uRaw * 1000 : (uRaw ? new Date(uRaw).getTime() : 0);
                        var uStr = uMs > 0 ? Qt.formatDateTime(new Date(uMs), "d.M.yyyy hh:mm") : "";

                        if (cStr !== "") {
                            timeStr = cStr;
                            // Näytetään perässä jos muokattu
                            if (uStr !== "" && uStr !== cStr) {
                                timeStr += " (Muokattu: " + uStr + ")";
                            }
                        }
                    }

                    memoModel.append({
                        "memoId": mId.toString(),
                        "content": memos[i].content || memos[i].name,
                        "timestamp": timeStr
                    });
                }
            } else if (data[0] === 'memo_queued') {
                page.errorMessage = "Ei verkkoa, lisätty lähetysjonoon.";
            } else if (data[0] === 'queue_synced') {
                py.call('memos.api.fetch_memos', []);
            } else if (data[0] === 'error') {
                page.errorMessage = data[1];
            } else if (data[0] === 'memo_edited' || data[0] === 'memo_deleted') {
                py.call('memos.api.fetch_memos', []);
            }
        }
    }

    Connections {
        target: appWindow
        onRequestNewMemo: {
            var dialog = pageStack.push(Qt.resolvedUrl("NewMemoDialog.qml"))
            dialog.accepted.connect(function() {
                py.call('memos.api.create_memo', [dialog.memoContent], function() {
                    py.call('memos.api.fetch_memos', [])
                })
            })
        }
    }

    Timer {
        id: syncTimer
        interval: 15000
        running: true
        repeat: true
        onTriggered: {
            py.call('memos.api.sync_queue', [])
        }
    }

    ListModel {
        id: memoModel
    }

    SilicaListView {
        anchors.fill: parent
        model: memoModel

        header: Column {
            width: parent.width

            PageHeader {
                title: "Memos"
            }

            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2*Theme.horizontalPageMargin
                color: Theme.highlightColor
                wrapMode: Text.WordWrap
                font.pixelSize: Theme.fontSizeExtraSmall

                text: page.errorMessage
                visible: text !== ""
                bottomPadding: visible ? Theme.paddingMedium : 0
            }
        }

        PullDownMenu {
            MenuItem {
                text: "Asetukset"
                onClicked: {
                    py.call('memos.api.get_settings', [], function(settings) {
                        var dialog = pageStack.push(Qt.resolvedUrl("SettingsDialog.qml"), {
                            currentUrl: settings.base_url,
                            currentToken: settings.token,
                            currentAutoUpload: settings.auto_upload,
                            currentLineCount: settings.line_count !== undefined ? settings.line_count : 2,
                            currentCoverMode: settings.cover_mode !== undefined ? settings.cover_mode : 0
                        })
                        dialog.accepted.connect(function() {
                            page.listLineCount = dialog.savedLineCount;
                            page.listCoverMode = dialog.savedCoverMode;

                            // HUOM: save_settings saa nyt 5 arvoa!
                            py.call('memos.api.save_settings', [dialog.savedUrl, dialog.savedToken, dialog.savedAutoUpload, dialog.savedLineCount, dialog.savedCoverMode], function() {
                                py.call('memos.api.fetch_memos', [])
                            })
                        })
                    })
                }
            }
            MenuItem {
                text: "Uusi memo"
                onClicked: {
                    var dialog = pageStack.push(Qt.resolvedUrl("NewMemoDialog.qml"))
                    dialog.accepted.connect(function() {
                        py.call('memos.api.create_memo', [dialog.memoContent], function() {
                            py.call('memos.api.fetch_memos', [])
                        })
                    })
                }
            }
            MenuItem {
                text: "Päivitä"
                onClicked: {
                    page.errorMessage = "Päivitetään..."
                    py.call('memos.api.sync_queue', [], function() {
                        py.call('memos.api.fetch_memos', [])
                    })
                }
            }
        }

        delegate: ListItem {
            id: listItem

            contentHeight: Math.max(memoColumn.height + (Theme.paddingLarge * 2), Theme.itemSizeSmall)

            menu: ContextMenu {
                MenuItem {
                    text: "Muokkaa"
                    visible: memoId !== "queued"
                    onClicked: {
                        var dialog = pageStack.push(Qt.resolvedUrl("NewMemoDialog.qml"), {initialText: content})
                        dialog.accepted.connect(function() {
                            py.call('memos.api.edit_memo', [memoId, dialog.memoContent], function() {
                                py.call('memos.api.fetch_memos', [])
                            })
                        })
                    }
                }
                MenuItem {
                    text: "Poista"
                    visible: memoId !== "queued"
                    onClicked: {
                        py.call('memos.api.delete_memo', [memoId], function() {
                            py.call('memos.api.fetch_memos', [])
                        })
                    }
                }
            }

            Column {
                id: memoColumn
                x: Theme.horizontalPageMargin
                width: parent.width - 2*Theme.horizontalPageMargin
                anchors.verticalCenter: parent.verticalCenter
                spacing: Theme.paddingSmall

                Label {
                    text: timestamp
                    color: Theme.secondaryColor
                    font.pixelSize: Theme.fontSizeExtraSmall
                    visible: text !== ""

                    // Varmistetaan että pitkä "(Muokattu: ...)" -teksti wrappaa nätisti
                    width: parent.width
                    wrapMode: Text.WordWrap
                }

                Label {
                    id: memoText
                    width: parent.width

                    textFormat: Text.StyledText
                    text: formatText(content)
                    linkColor: Theme.highlightColor

                    color: listItem.highlighted ? Theme.highlightColor : Theme.primaryColor
                    wrapMode: Text.WordWrap

                    maximumLineCount: page.listLineCount === 0 ? 1000 : page.listLineCount
                    truncationMode: TruncationMode.Fade
                    font.pixelSize: Theme.fontSizeSmall
                }
            }

            onClicked: {
                pageStack.push(Qt.resolvedUrl("MemoPage.qml"), {
                    memoId: memoId,
                    memoContent: content,
                    memoTimestamp: timestamp
                })
            }
        }
    }
}
