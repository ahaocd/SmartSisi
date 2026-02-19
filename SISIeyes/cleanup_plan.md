# SISIeyes项目清理计划

## 🗑️ 需要删除的文件

### 冗余的视频播放代码
- [ ] main/avi_player_esp32.c (424行，自制AVI播放器)
- [ ] main/avi_player_esp32.h 
- [ ] main/avilib.c (AVI解析库)
- [ ] main/avilib.h
- [ ] main/video_frames.h (静态帧数据)

### 无用的视频文件
- [ ] spiffs_data/background.avi (可能不兼容)
- [ ] build/ (整个编译目录)

### 冗余的组件
- [ ] components/avilib/ (如果存在)

## 🔧 需要修改的文件

### main/sisi_ui.c
- [ ] 删除video_system_t结构体
- [ ] 删除所有AVI播放相关函数
- [ ] 删除FreeRTOS定时器代码
- [ ] 保留LVGL UI功能

### main/app_main.c  
- [ ] 删除AVI播放器初始化
- [ ] 删除视频系统启动代码

### main/CMakeLists.txt
- [ ] 删除avilib相关依赖

## 🚀 替换为esp_video架构

### 新增文件
- [ ] main/hagl_video.c (基于esp_video)
- [ ] main/hagl_video.h
- [ ] main/video_manager.c (任务切换管理)
- [ ] main/video_manager.h

### 集成HAGL
- [ ] 添加HAGL组件
- [ ] 配置显示驱动
- [ ] 实现任务切换

## 📁 新的视频文件位置
- [ ] sdcard/video/ (使用SD卡存储)
- [ ] 转换为MJPEG格式
- [ ] 172x320分辨率

## 🎯 清理后的架构
```
SISIeyes/
├── main/
│   ├── app_main.c          (主程序)
│   ├── sisi_ui.c           (LVGL UI系统)
│   ├── hagl_video.c        (HAGL视频系统)
│   ├── video_manager.c     (任务切换管理)
│   └── camera_handler.c    (摄像头功能)
├── components/
│   ├── hagl/              (HAGL图形库)
│   ├── hagl_hal/          (HAGL硬件抽象)
│   └── lvgl/              (LVGL UI库)
└── sdcard/
    ├── video/
    │   ├── background.mjp  (背景视频)
    │   └── idle.mjp       (空闲视频)
    └── photos/            (拍摄的照片)
```
