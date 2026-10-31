# desktop-harness JSON Schemas

> 下列 schema 是文件化的 canonical contract，不是 repo 內既有 machine-readable schema 檔，也不代表所有 helper 已有完整 runtime validation。標有「最小契約」者，欄位 requiredness 仍受未提供 source 限制。

## 1. 核心資料記錄

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:desktop-harness:data-model:0.4.2",
  "title": "desktop-harness core data records",
  "$defs": {
    "AppInfo": {
      "type": "object",
      "description": "Running application metadata.",
      "required": ["name", "bundle_id", "pid", "active", "hidden"],
      "additionalProperties": false,
      "properties": {
        "name": {
          "type": "string",
          "description": "Localized application name; may be empty."
        },
        "bundle_id": {
          "type": "string",
          "description": "macOS bundle identifier; may be empty."
        },
        "pid": {
          "type": "integer",
          "minimum": 0
        },
        "active": {
          "type": "boolean"
        },
        "hidden": {
          "type": "boolean"
        }
      }
    },
    "WindowInfo": {
      "type": "object",
      "description": "CoreGraphics on-screen window metadata.",
      "required": ["id", "app", "pid", "title", "x", "y", "w", "h"],
      "additionalProperties": false,
      "properties": {
        "id": {
          "type": "integer",
          "minimum": 0
        },
        "app": {
          "type": "string"
        },
        "pid": {
          "type": "integer",
          "minimum": 0
        },
        "title": {
          "type": "string",
          "description": "Window title; may be empty when unavailable."
        },
        "x": {
          "type": "number"
        },
        "y": {
          "type": "number"
        },
        "w": {
          "type": "number",
          "minimum": 0
        },
        "h": {
          "type": "number",
          "minimum": 0
        }
      }
    },
    "MousePosition": {
      "type": "object",
      "description": "Minimum proven mouse-position contract.",
      "required": ["x", "y"],
      "additionalProperties": false,
      "properties": {
        "x": {
          "type": "number"
        },
        "y": {
          "type": "number"
        }
      }
    },
    "Frame": {
      "type": "object",
      "description": "Screen-coordinate rectangle.",
      "required": ["x", "y", "w", "h"],
      "additionalProperties": false,
      "properties": {
        "x": {
          "type": "number"
        },
        "y": {
          "type": "number"
        },
        "w": {
          "type": "number",
          "minimum": 0
        },
        "h": {
          "type": "number",
          "minimum": 0
        }
      }
    },
    "AxNode": {
      "type": "object",
      "description": "Minimum documented Accessibility node envelope; additional implementation fields are allowed.",
      "required": ["role"],
      "additionalProperties": true,
      "properties": {
        "role": {
          "type": "string"
        },
        "title": {
          "type": ["string", "null"]
        },
        "value": {
          "type": ["string", "number", "boolean", "null"]
        },
        "frame": {
          "$ref": "#/$defs/Frame"
        }
      }
    },
    "MediaTransportState": {
      "type": "object",
      "required": ["state", "transport_play", "row_play", "play"],
      "additionalProperties": false,
      "properties": {
        "state": {
          "type": "string",
          "enum": ["playing", "paused", "unknown"]
        },
        "transport_play": {
          "type": "boolean"
        },
        "row_play": {
          "type": "boolean"
        },
        "play": {
          "type": "boolean",
          "description": "Compatibility alias for transport_play."
        }
      }
    },
    "AuditRow": {
      "type": "object",
      "required": ["ts", "event", "detail"],
      "additionalProperties": false,
      "properties": {
        "ts": {
          "type": "number",
          "description": "Unix epoch timestamp in seconds."
        },
        "event": {
          "type": "string",
          "minLength": 1
        },
        "detail": {
          "type": "object",
          "additionalProperties": true
        }
      }
    }
  }
}
```

### 1.1 Core invariant

Media state 應符合：

```text
play == transport_play
```

此關聯目前由 self-test 驗證，不是 JSON Schema 原生可表達的跨欄位 constraint。

## 2. Daemon request／response

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:desktop-harness:daemon:0.4.2",
  "title": "desktop-harness daemon messages",
  "$defs": {
    "DaemonRequest": {
      "type": "object",
      "required": ["op", "token"],
      "additionalProperties": true,
      "properties": {
        "op": {
          "type": "string",
          "enum": ["ping", "quit", "exec"]
        },
        "token": {
          "type": "string",
          "minLength": 1,
          "description": "Opaque local authentication secret. Content is intentionally not documented."
        },
        "code": {
          "type": "string",
          "description": "Python source executed only when op is exec."
        }
      },
      "allOf": [
        {
          "if": {
            "properties": {
              "op": {
                "const": "exec"
              }
            },
            "required": ["op"]
          },
          "then": {
            "required": ["code"]
          }
        }
      ]
    },
    "DaemonResponse": {
      "oneOf": [
        {
          "type": "object",
          "required": ["ok", "pong"],
          "additionalProperties": false,
          "properties": {
            "ok": {
              "const": true
            },
            "pong": {
              "const": true
            }
          }
        },
        {
          "type": "object",
          "required": ["ok"],
          "additionalProperties": false,
          "properties": {
            "ok": {
              "const": true
            }
          }
        },
        {
          "type": "object",
          "required": ["ok", "stdout", "stderr"],
          "additionalProperties": false,
          "properties": {
            "ok": {
              "type": "boolean"
            },
            "stdout": {
              "type": "string"
            },
            "stderr": {
              "type": "string"
            }
          }
        },
        {
          "type": "object",
          "required": ["ok", "error"],
          "additionalProperties": false,
          "properties": {
            "ok": {
              "const": false
            },
            "error": {
              "type": "string"
            }
          }
        }
      ]
    }
  }
}
```

### 2.1 Protocol distinctions

1. `quit` success 只有 `ok`。
2. Exec 失敗仍是 `{ok:false, stdout, stderr}`，不是 `{ok:false, error}`。
3. Parse error、token mismatch 與 unknown op 才使用 `{ok:false, error}`。
4. Source 未限制 request line 大小；schema 本身也不設定 maximum length。

## 3. Voice function tool definition

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:desktop-harness:voice-tools:0.4.2",
  "title": "desktop-harness voice function tools",
  "$defs": {
    "ToolName": {
      "type": "string",
      "enum": [
        "list_apps",
        "open_app",
        "screen_labels",
        "click_text",
        "type_text",
        "hotkey",
        "move_mouse",
        "click_xy",
        "mouse_pos",
        "wiggle_mouse"
      ]
    },
    "FunctionToolDefinition": {
      "type": "object",
      "required": ["type", "name", "description", "parameters"],
      "additionalProperties": false,
      "properties": {
        "type": {
          "const": "function"
        },
        "name": {
          "$ref": "#/$defs/ToolName"
        },
        "description": {
          "type": "string"
        },
        "parameters": {
          "type": "object",
          "required": ["type", "properties", "required"],
          "additionalProperties": true,
          "properties": {
            "type": {
              "const": "object"
            },
            "properties": {
              "type": "object",
              "additionalProperties": true
            },
            "required": {
              "type": "array",
              "items": {
                "type": "string"
              }
            }
          }
        }
      }
    },
    "FunctionToolOutput": {
      "oneOf": [
        {
          "type": "object",
          "required": ["ok", "result"],
          "additionalProperties": false,
          "properties": {
            "ok": {
              "const": true
            },
            "result": {}
          }
        },
        {
          "type": "object",
          "required": ["ok", "error"],
          "additionalProperties": false,
          "properties": {
            "ok": {
              "const": false
            },
            "error": {
              "type": "string"
            }
          }
        }
      ]
    }
  }
}
```

### 3.1 各 tool 的 parameter schema

下表採 JSON Schema 概念表示；`default` 是 annotation。

| Tool | `parameters.properties` | `parameters.required` |
|---|---|---|
| `list_apps` | `{}` | `[]` |
| `open_app` | `name: string` | `["name"]` |
| `screen_labels` | `app?: string`、`limit?: integer` | `[]` |
| `click_text` | `text: string`、`app?: string` | `["text"]` |
| `type_text` | `text: string` | `["text"]` |
| `hotkey` | `keys: string[]` | `["keys"]` |
| `move_mouse` | `x: number`、`y: number`、`duration?: number` | `["x", "y"]` |
| `click_xy` | `x: number`、`y: number`、`double?: boolean` | `["x", "y"]` |
| `mouse_pos` | `{}` | `[]` |
| `wiggle_mouse` | `{}` | `[]` |

### 3.2 Dry-run result

```json
{
  "type": "object",
  "required": ["ok", "result"],
  "additionalProperties": false,
  "properties": {
    "ok": {
      "const": true
    },
    "result": {
      "type": "object",
      "required": ["dry_run", "tool", "arguments"],
      "additionalProperties": false,
      "properties": {
        "dry_run": {
          "const": true
        },
        "tool": {
          "type": "string"
        },
        "arguments": {
          "type": "object",
          "additionalProperties": true
        }
      }
    }
  }
}
```

## 4. Voice session messages

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:desktop-harness:voice-session:0.4.2",
  "title": "desktop-harness voice session messages",
  "$defs": {
    "FunctionToolDefinitionRef": {
      "type": "object"
    },
    "VoiceFunctionCallEvent": {
      "type": "object",
      "required": ["type", "name", "call_id", "arguments"],
      "additionalProperties": true,
      "properties": {
        "type": {
          "const": "response.function_call_arguments.done"
        },
        "name": {
          "type": "string"
        },
        "call_id": {
          "type": "string"
        },
        "arguments": {
          "type": ["string", "object"],
          "description": "The executor accepts either a JSON object or a JSON string."
        }
      }
    },
    "VoiceFunctionOutputItem": {
      "type": "object",
      "required": ["type", "call_id", "output"],
      "additionalProperties": false,
      "properties": {
        "type": {
          "const": "function_call_output"
        },
        "call_id": {
          "type": "string"
        },
        "output": {
          "type": "string",
          "description": "JSON-encoded FunctionToolOutput."
        }
      }
    },
    "VoiceTextConversationItem": {
      "type": "object",
      "required": ["type", "message"],
      "additionalProperties": false,
      "properties": {
        "type": {
          "const": "conversation.item.create"
        },
        "message": {
          "type": "object"
        }
      }
    },
    "VoiceSessionUpdate": {
      "type": "object",
      "required": ["type", "session"],
      "additionalProperties": false,
      "properties": {
        "type": {
          "const": "session.update"
        },
        "session": {
          "type": "object",
          "required": ["voice", "instructions", "tools", "turn_detection"],
          "additionalProperties": false,
          "properties": {
            "voice": {
              "type": "string"
            },
            "instructions": {
              "type": "string"
            },
            "tools": {
              "type": "array",
              "items": {
                "$ref": "#/$defs/FunctionToolDefinitionRef"
              }
            },
            "turn_detection": {
              "type": ["object", "null"],
              "additionalProperties": true
            }
          }
        }
      }
    }
  }
}
```

### 4.1 實作中的 message 差異

`VoiceTextConversationItem` 在上例刻意將 item body 概括為 object，因其完整 nested schema 不屬於核心資料模型；實際 body 為：

- `type: message`
- `role: user`
- `content: [{type: input_text, text: string}]`

Function output item 則固定使用 `call_id` 與 JSON-encoded output string。

## 5. Audit detail variants

Audit `detail` 會依 event 改變。已確認的最小 variants：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:desktop-harness:audit-detail:0.4.2",
  "title": "Known audit detail variants",
  "oneOf": [
    {
      "type": "object",
      "required": ["name", "reason"],
      "additionalProperties": false,
      "properties": {
        "name": {
          "type": "string"
        },
        "reason": {
          "type": "string"
        }
      }
    },
    {
      "type": "object",
      "required": ["name", "cold"],
      "additionalProperties": false,
      "properties": {
        "name": {
          "type": "string"
        },
        "cold": {
          "type": "boolean"
        },
        "warn": {
          "type": "string"
        }
      }
    },
    {
      "type": "object",
      "required": ["app", "window_id", "path"],
      "additionalProperties": false,
      "properties": {
        "app": {
          "type": ["string", "null"]
        },
        "window_id": {
          "type": ["integer", "null"]
        },
        "path": {
          "type": "string"
        }
      }
    }
  ]
}
```

此 variants schema 只涵蓋 source 可直接確認的 event；`detail` 的 extensible 設計表示未來仍可新增其他 shape。

## 6. 不應建立 schema 的項目

下列值是 runtime-specific 或 source-dependent，因此不應固定成 canonical schema：

- AX title、value 與 UI label 實際內容；
- app name、window title、bundle id 的實際值；
- screenshot binary content；
- audit 的時間戳與實際 detail 值；
- daemon token；
- typed text 與 voice transcript；
- click hit 的未驗證額外欄位。
