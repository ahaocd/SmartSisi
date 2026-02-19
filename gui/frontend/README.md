# SmartSisi 新前端（阶段一：Mock 原型）

## 目标
- 用 **Vite + Vue3 + Naive UI（纯 JS）** 重做 `5000` 前端为 SPA
- 先用 **Mock API / Mock WS** 跑通：系统切换、聊天、右侧事件中心、Live2D 加载
- UI 定型后再对接真实后端（`/api/*` + `ws://127.0.0.1:10003`）

## 运行（开发）
```powershell
cd E:\liusisi\SmartSisi\gui\frontend
npm install
npm run dev
```

## 构建（产物输出到 Flask static）
```powershell
cd E:\liusisi\SmartSisi\gui\frontend
npm run build
```

构建产物会输出到：
- `E:\liusisi\SmartSisi\gui\static\app\`

## Live2D
- 入口脚本：`public/live2d/autoload.js`（CDN 加载 live2d-widget）
- 文案配置：`public/live2d/waifu-tips.json`

## 对接契约
见：`docs/contract.md`

