/**
 * Load Nuke Camera - "choose chan file to upload" button, like VHS Load Video (Upload).
 * Uploads into the ComfyUI input folder and puts the uploaded name in chan_file.
 */

import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

app.registerExtension({
    name: "motioncapture.loadnukecamera",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData?.name !== "LoadNukeCamera") {
            return;
        }
        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = onNodeCreated?.apply(this, arguments);
            const chanWidget = this.widgets.find((w) => w.name === "chan_file");
            const fileInput = document.createElement("input");
            Object.assign(fileInput, {
                type: "file",
                accept: ".chan",
                style: "display: none",
                onchange: async () => {
                    const file = fileInput.files[0];
                    fileInput.value = "";
                    if (!file) {
                        return;
                    }
                    const body = new FormData();
                    body.append("image", file);
                    const resp = await api.fetchApi("/upload/image", { method: "POST", body });
                    if (resp.status !== 200) {
                        alert(`Upload failed: ${resp.status} ${resp.statusText}`);
                        return;
                    }
                    const { name } = await resp.json();
                    chanWidget.value = name;
                    chanWidget.callback?.(name);
                },
            });
            document.body.append(fileInput);
            const onRemoved = this.onRemoved;
            this.onRemoved = function () {
                fileInput.remove();
                return onRemoved?.apply(this, arguments);
            };
            this.addWidget("button", "choose chan file to upload", null, () => fileInput.click());
            return r;
        };
    },
});
