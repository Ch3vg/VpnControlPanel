import { basicSetup } from "codemirror";
import { EditorView, keymap } from "@codemirror/view";
import { EditorState } from "@codemirror/state";
import { json, jsonParseLinter } from "@codemirror/lang-json";
import { yaml } from "@codemirror/lang-yaml";
import { linter, lintGutter } from "@codemirror/lint";
import { oneDark } from "@codemirror/theme-one-dark";
import { indentWithTab } from "@codemirror/commands";
import jsyaml from "js-yaml";

function yamlParseLinter() {
  return linter((view) => {
    const text = view.state.doc.toString();
    if (!text.trim()) {
      return [];
    }
    try {
      const doc = jsyaml.load(text);
      if (doc === null || typeof doc !== "object" || Array.isArray(doc)) {
        return [
          {
            from: 0,
            to: Math.min(text.length, 1),
            severity: "error",
            message: "Корень YAML должен быть объектом (mapping)",
          },
        ];
      }
      return [];
    } catch (error) {
      const message = error?.message || String(error);
      const mark = error?.mark;
      let from = 0;
      let to = Math.min(text.length, 1);
      if (mark && typeof mark.line === "number") {
        const line = view.state.doc.line(Math.min(mark.line + 1, view.state.doc.lines));
        from = line.from + Math.min(Math.max(mark.column || 0, 0), line.length);
        to = Math.min(from + 1, line.to);
      }
      return [{ from, to, severity: "error", message }];
    }
  });
}

function objectRootJsonLinter() {
  return linter((view) => {
    const text = view.state.doc.toString();
    if (!text.trim()) {
      return [];
    }
    try {
      const doc = JSON.parse(text);
      if (!doc || typeof doc !== "object" || Array.isArray(doc)) {
        return [
          {
            from: 0,
            to: Math.min(text.length, 1),
            severity: "error",
            message: "Корень JSON должен быть объектом",
          },
        ];
      }
      return [];
    } catch {
      return [];
    }
  });
}

/**
 * @param {HTMLElement} parent
 * @param {{ format: "json" | "yaml", doc?: string, onChange?: (text: string) => void }} options
 */
export function createConfigEditor(parent, options) {
  const format = options.format === "yaml" ? "yaml" : "json";
  const language =
    format === "yaml"
      ? [yaml(), lintGutter(), yamlParseLinter()]
      : [json(), lintGutter(), linter(jsonParseLinter()), objectRootJsonLinter()];

  const updateListener = EditorView.updateListener.of((update) => {
    if (update.docChanged && typeof options.onChange === "function") {
      options.onChange(update.state.doc.toString());
    }
  });

  const state = EditorState.create({
    doc: options.doc || "",
    extensions: [
      basicSetup,
      oneDark,
      keymap.of([indentWithTab]),
      ...language,
      updateListener,
      EditorView.theme({
        "&": {
          height: "100%",
          fontSize: "0.85rem",
          border: "1px solid #2d3a4f",
          borderRadius: "8px",
          overflow: "hidden",
        },
        ".cm-scroller": { minHeight: "320px", maxHeight: "560px" },
        ".cm-content": { fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" },
      }),
    ],
  });

  const view = new EditorView({
    state,
    parent,
  });

  return {
    format,
    getValue() {
      return view.state.doc.toString();
    },
    setValue(text) {
      view.dispatch({
        changes: { from: 0, to: view.state.doc.length, insert: text ?? "" },
      });
    },
    focus() {
      view.focus();
    },
    destroy() {
      view.destroy();
    },
    hasLintErrors() {
      // Force a sync check using the same parsers.
      const text = view.state.doc.toString();
      if (!text.trim()) return true;
      try {
        if (format === "yaml") {
          const doc = jsyaml.load(text);
          return !doc || typeof doc !== "object" || Array.isArray(doc);
        }
        const doc = JSON.parse(text);
        return !doc || typeof doc !== "object" || Array.isArray(doc);
      } catch {
        return true;
      }
    },
  };
}

export function serializeConfigData(configData, format) {
  if (format === "yaml") {
    return jsyaml.dump(configData, { lineWidth: 100, noRefs: true, sortingKeys: false });
  }
  return JSON.stringify(configData, null, 2);
}

export function parseConfigContent(content, format) {
  const text = String(content || "");
  if (!text.trim()) {
    throw new Error("Пустой документ");
  }
  if (format === "yaml") {
    const doc = jsyaml.load(text);
    if (!doc || typeof doc !== "object" || Array.isArray(doc)) {
      throw new Error("Корень YAML должен быть объектом");
    }
    return doc;
  }
  const doc = JSON.parse(text);
  if (!doc || typeof doc !== "object" || Array.isArray(doc)) {
    throw new Error("Корень JSON должен быть объектом");
  }
  return doc;
}
