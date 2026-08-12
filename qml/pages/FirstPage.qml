import QtQuick 2.0
import Sailfish.Silica 1.0
import io.thp.pyotherside 1.0

Page {
    id: page
    allowedOrientations: Orientation.All

    property string errorMessage: ""
    property int listLineCount: 2
    property int listCoverMode: 0
    // Tracks whether there's anything waiting in the offline queue, so the
    // periodic sync timer doesn't keep firing (and waking up Python) for
    // no reason when there's nothing to sync.
    property bool hasQueuedItems: false

    // Tähän tallennetaan kaikki haetut muistiinpanot
    property var allMemos: []
    // Tähän tallennetaan hakusana turvallisesti
    property string searchText: ""

    // Funktio, joka päivittää listanäkymän hakukentän perusteella
    function updateList() {
        memoModel.clear();
        var filter = page.searchText.toLowerCase();

        for (var i = 0; i < allMemos.length; i++) {
            var m = allMemos[i];

            // Varmistetaan, että teksti on olemassa ja muutetaan se merkkijonoksi
            var contentString = m.content ? m.content.toString().toLowerCase() : "";

            if (filter !== "" && contentString.indexOf(filter) === -1) {
                continue;
            }

            memoModel.append(m);
        }
    }

    // Saves a NewMemoDialog opened for a *brand new* memo. If an attachment
    // was added during composition, NewMemoDialog already silently created
    // the memo at that point (so the attachment could link to something
    // real) - in that case this just saves the final text into it. Otherwise
    // (no attachments were added) it creates the memo now as normal.
    function createMemoFromDialog(dialog) {
        if (dialog.memoWasCreatedDuringComposition && dialog.memoId !== "") {
            py.call('memos.api.edit_memo', [dialog.memoId, dialog.memoContent], function() {
                py.call('memos.api.fetch_memos', [])
            })
        } else {
            py.call('memos.api.create_memo', [dialog.memoContent], function() {
                py.call('memos.api.fetch_memos', [])
            })
        }
    }

    // If the dialog is cancelled after attachments were uploaded during
    // composition, clean those up too - they'd otherwise stay uploaded and
    // linked (or orphaned, for a cancelled brand-new memo) despite never
    // being saved into any visible memo content. force_queue=true on the
    // memo delete ensures that specific cleanup is retried later even with
    // auto-upload disabled, since it's not something the user asked for.
    function cleanupCancelledMemoDialog(dialog) {
        var attachments = dialog.uploadedAttachments;
        for (var i = 0; i < attachments.length; i++) {
            py.call('memos.api.delete_attachment', [attachments[i]])
        }
        if (dialog.memoWasCreatedDuringComposition && dialog.memoId !== "") {
            py.call('memos.api.delete_memo', [dialog.memoId, true], function() {
                py.call('memos.api.fetch_memos', [])
            })
        }
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
                memoModel.clear(); // Tyhjennetään vain haun alussa
                var memos = data[1];
                var processedMemos = [];

                if (memos.length > 0) {
                    var latestContent = memos[0].content || memos[0].name;

                    if (page.listCoverMode === 1) {
                        var maxMs = 0;
                        var maxIdx = 0;
                        for (var m = 0; m < memos.length; m++) {
                            if (memos[m].name === "queued") {
                                maxMs = Date.now();
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
                    appWindow.latestMemoText = qsTr("No memos");
                }

                for (var i = 0; i < memos.length; i++) {
                    var mId = memos[i].name || memos[i].id || "unknown";
                    var timeStr = "";

                    if (mId !== "queued") {
                        var cRaw = memos[i].createTime || memos[i].createdTs || "";
                        var cMs = typeof cRaw === "number" ? cRaw * 1000 : (cRaw ? new Date(cRaw).getTime() : 0);
                        var cStr = cMs > 0 ? Qt.formatDateTime(new Date(cMs), "d.M.yyyy hh:mm") : "";

                        var uRaw = memos[i].updateTime || memos[i].updatedTs || "";
                        var uMs = typeof uRaw === "number" ? uRaw * 1000 : (uRaw ? new Date(uRaw).getTime() : 0);
                        var uStr = uMs > 0 ? Qt.formatDateTime(new Date(uMs), "d.M.yyyy hh:mm") : "";

                        if (cStr !== "") {
                            timeStr = cStr;
                            if (uStr !== "" && uStr !== cStr) {
                                timeStr += " " + qsTr("(Edited: %1)").arg(uStr);
                            }
                        }
                    }

                    processedMemos.push({
                        "memoId": mId.toString(),
                        "content": memos[i].content || memos[i].name,
                        "timestamp": timeStr
                    });
                }

                // Tallennetaan muistiin ja päivitetään lista
                page.allMemos = processedMemos;
                page.updateList();

            } else if (data[0] === 'memo_queued') {
                page.errorMessage = qsTr("No network, added to queue.");
                page.hasQueuedItems = true;
            } else if (data[0] === 'queue_synced') {
                page.hasQueuedItems = false;
                py.call('memos.api.fetch_memos', []);
            } else if (data[0] === 'queue_status') {
                // Authoritative from the backend: whether the offline queue
                // has anything pending right now, including queued deletes
                // (which don't show up as a visible marker in the memo
                // list itself, unlike queued creates/edits).
                page.hasQueuedItems = !!data[1];
            } else if (data[0] === 'error') {
                page.errorMessage = data[1];
            } else if (data[0] === 'success') {
                // data[1] is a translation key from the backend, not
                // user-facing text, so it's translated here in QML.
                if (data[1] === 'cache_cleared') {
                    page.errorMessage = qsTr("Caches cleared!");
                } else {
                    page.errorMessage = data[1];
                }
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
                page.createMemoFromDialog(dialog)
            })
            dialog.rejected.connect(function() {
                page.cleanupCancelledMemoDialog(dialog)
            })
        }
    }

    Timer {
        id: syncTimer
        interval: 15000
        // Only poll for a retry while something is actually queued, instead
        // of waking up the Python side every 15s indefinitely.
        running: page.hasQueuedItems
        repeat: true
        onTriggered: {
            py.call('memos.api.sync_queue', [])
        }
    }

    ListModel {
        id: memoModel
    }

    SilicaListView {
        id: listView
        anchors.fill: parent
        model: memoModel

        header: Column {
            width: parent.width

            PageHeader {
                title: "Memos"
            }

            SearchField {
                id: searchField
                width: parent.width
                placeholderText: qsTr("Search...")

                // Päivitetään hakusana suoraan muuttujaan ilman listan tyhjentämistä!
                onTextChanged: {
                    page.searchText = text.toLowerCase();
                }

                EnterKey.onClicked: focus = false
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
                text: qsTr("Clear cache")
                onClicked: {
                    page.errorMessage = qsTr("Clearing cache...")
                    py.call('memos.api.clear_cache', [], function() {
                        // Kun välimuisti on tyhjennetty, ladataan muistiinpanot
                        // ja kuvat puhtaalta pöydältä uudestaan palvelimelta:
                        py.call('memos.api.fetch_memos', [])
                    })
                }
            }
            MenuItem {
                text: qsTr("Settings")
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

                            py.call('memos.api.save_settings', [dialog.savedUrl, dialog.savedToken, dialog.savedAutoUpload, dialog.savedLineCount, dialog.savedCoverMode], function() {
                                py.call('memos.api.fetch_memos', [])
                            })
                        })
                    })
                }
            }
            MenuItem {
                text: qsTr("New memo")
                onClicked: {
                    var dialog = pageStack.push(Qt.resolvedUrl("NewMemoDialog.qml"))
                    dialog.accepted.connect(function() {
                        page.createMemoFromDialog(dialog)
                    })
                    dialog.rejected.connect(function() {
                        page.cleanupCancelledMemoDialog(dialog)
                    })
                }
            }
            MenuItem {
                text: qsTr("Refresh")
                onClicked: {
                    page.errorMessage = qsTr("Updating...")
                    py.call('memos.api.sync_queue', [], function() {
                        py.call('memos.api.fetch_memos', [])
                    })
                }
            }
        }

        delegate: ListItem {
            id: listItem

            // --- SUODATUSLOGIIKKA: Ollaanko näkyvissä? ---
            property string contentString: content ? content.toString().toLowerCase() : ""
            property bool isMatch: page.searchText === "" || contentString.indexOf(page.searchText) !== -1

            // Piilotetaan item täysin, jos se ei vastaa hakua
            visible: isMatch
            contentHeight: isMatch ? Math.max(memoColumn.height + (Theme.paddingLarge * 2), Theme.itemSizeSmall) : 0
            height: isMatch ? contentHeight : 0
            // ---------------------------------------------

            menu: ContextMenu {
                MenuItem {
                    text: qsTr("Edit")
                    visible: memoId !== "queued"
                    onClicked: {
                        var dialog = pageStack.push(Qt.resolvedUrl("NewMemoDialog.qml"), {initialText: content, memoId: memoId})
                        dialog.accepted.connect(function() {
                            py.call('memos.api.edit_memo', [memoId, dialog.memoContent], function() {
                                py.call('memos.api.fetch_memos', [])
                            })
                        })
                        dialog.rejected.connect(function() {
                            page.cleanupCancelledMemoDialog(dialog)
                        })
                    }
                }
                MenuItem {
                    text: qsTr("Delete")
                    visible: memoId !== "queued"
                    onClicked: {
                        listItem.remorseAction(qsTr("Deleting"), function() {
                            py.call('memos.api.delete_memo', [memoId], function() {
                                py.call('memos.api.fetch_memos', [])
                            })
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

                    width: parent.width
                    wrapMode: Text.WordWrap
                }

                Label {
                    id: memoText
                    width: parent.width

                    textFormat: Text.StyledText
                    linkColor: Theme.highlightColor
                    color: listItem.highlighted ? Theme.highlightColor : Theme.primaryColor
                    wrapMode: Text.WordWrap

                    maximumLineCount: page.listLineCount === 0 ? 1000 : page.listLineCount
                    truncationMode: TruncationMode.Fade
                    font.pixelSize: Theme.fontSizeSmall

                    property string rawContent: content
                    onRawContentChanged: fetchHtml()
                    onWidthChanged: {
                        if (width > 0 && isMatch)
                            fetchHtml()
                    }
                    Component.onCompleted: fetchHtml()

                    function fetchHtml() {
                        if (py && isMatch && memoText.width > 0) {
                            // Kuville annetaan aina todellinen käytettävissä oleva leveys.
                            // Python-renderöijä lisää img-tagille sekä width- että height-arvon,
                            // jolloin Qt StyledText ei käytä kuvan alkuperäistä kokoa.
                            var w = Math.floor(memoText.width)

                            py.call('memos.api.render_markdown', [rawContent, w], function(html) {
                                memoText.text = html
                            })
                        }
                    }
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
