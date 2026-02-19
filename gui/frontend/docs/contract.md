# SmartSisi UI 瀵规帴濂戠害锛堥樁娈典竴锛歁ock锛涢樁娈典簩锛氬鎺ョ湡瀹炲悗绔級

> 鍓嶇鍏堟寜姝ょ粨鏋勮窇 Mock锛涘悗绔€愭瀹炵幇鍚屽悕瀛楁涓庝簨浠剁被鍨嬪嵆鍙棤鐥涙帴鍏ャ€?
## 1) 鍩虹姒傚康
- `system_id`: `"sisi" | "liuye"`
- 闊抽绛栫暐锛歚active_only`锛堜粎褰撳墠绯荤粺鍙/鍚級
  - `active_system_id`锛氬綋鍓嶆嫢鏈?STT/TTS 鏉冮檺鐨勭郴缁?
## 2) WebSocket锛圲I 浜嬩欢鎬荤嚎锛?### 2.1 瀹㈡埛绔彙鎵嬶紙娴忚鍣?鈫?鏈嶅姟绔級
```json
{
  "type": "hello",
  "username": "User",
  "system_id": "sisi",
  "output": 1
}
```

### 2.2 鏈嶅姟绔帹閫侊紙鏈嶅姟绔?鈫?娴忚鍣級
```json
{
  "type": "ui_event",
  "system_id": "liuye",
  "event": {
    "kind": "guild",
    "level": "info",
    "title": "鍐掗櫓鑰呭叕浼?,
    "message": "浠诲姟宸插垱寤?,
    "payload": { "task_id": "guild_123" }
  }
}
```

瀛楁璇存槑锛?- `kind`: `"chat" | "agent" | "guild" | "tool" | "audio" | "status" | "debug"`
- `level`: `"info" | "success" | "warning" | "error" | "debug"`
- `payload`: 浠绘剰 JSON锛堢敤浜庝簨浠惰鎯呴潰鏉匡級

## 3) HTTP API锛堥樁娈典簩鎺ュ叆锛?### 3.1 鍙戦€佹秷鎭?`POST /api/send`
```json
{ "system_id": "sisi", "username": "User", "msg": "浣犲ソ" }
```

### 3.2 鎷夊彇鍘嗗彶
`POST /api/get-msg`
```json
{ "system_id": "liuye", "username": "User", "limit": 200, "cursor": null }
```

### 3.3 鍏变韩閰嶇疆锛堥煶棰?璁惧/寮€鍏筹級
`POST /api/get-data` / `POST /api/submit`
- 浠嶇劧鏄叡浜煙锛涘璇濅笌璁板繂闅旂锛屼絾璁惧涓?TTS/STT 鍏变韩銆?

### 3.4 TTS 音色（角色）
`GET /api/tts/voices`
```json
{
  "sisi_voice_uri": "speech:...",
  "liuye_voice_uri": "speech:..."
}
```

`POST /api/tts/voices`
方式 1：
```json
{ "role": "sisi", "voice_uri": "speech:xxx" }
```
方式 2：
```json
{ "sisi_voice_uri": "speech:xxx", "liuye_voice_uri": "speech:yyy" }
```
说明：写回 `system.conf`，并同步当前运行态音色。
