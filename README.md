# Sailfish Memos

A native Sailfish OS client application for [Memos](https://usememos.com/). It allows you to browse, create, edit, and delete memos directly from your phone, wrapped in Sailfish's elegant UI.

## Features

* **Full Memos Integration:** Fetch, create, edit, and delete memos directly via the API.
* **Offline Support & Auto-Sync:** Write memos even without an internet connection. The app queues them and syncs automatically when the connection is restored.
* **Robust Markdown Support:** Powered by the standard-compliant `mistune` parser. Smoothly renders headings, bold/italic text, clickable links, custom colored tags, and task lists (`- [ ]` and `- [x]`).
* **Cover Page:** View your latest (or most recently edited) memo directly in the multitask view with Markdown styling, plus a quick action button to create a new memo.
* **Customizable Settings:** Choose the number of lines displayed in the list (1, 2, 3, or all) and configure the cover page behavior.
* **Timestamps:** Displays creation time and automatically indicates if a memo has been edited.
* **Native Localization:** Built-in Qt translation support (currently includes English and Finnish).

## Technologies

* **QML / Silica:** Sailfish OS native user interface framework.
* **PyOtherSide:** Bridges QML and Python seamlessly.
* **Python 3:** Backend logic, network requests (`urllib`), and local caching (`json`).
* **Mistune:** A fast, standard-compliant Markdown parser for Python used to render memos into rich text HTML.

## Building & Installation

1. Clone the repository:
   ```bash
   git clone [https://github.com/jarnose/harbour-memos.git](https://github.com/jarnose/harbour-memos.git) ```
2. Open the project in Qt Creator.
3. Build and deploy the package to the Sailfish OS emulator or a physical device.

*(Note: The* mistune *library is bundled directly within the* python/libs *directory, so no external dependency installation is required on the device).*

## License

This project is licensed under the MIT License - see the LICENSE file for details.
