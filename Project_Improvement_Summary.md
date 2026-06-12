# ADAMS Project: Backend & Mobile Integration Summary

## Overview
The goal of this update was to transition the ADAMS (Advanced Driver Alertness Monitoring System) from a static prototype to a dynamic, real-world navigation system. We have integrated a robust Python backend with the Flutter mobile application and implemented realistic routing using the KakaoMap API.

## Key Improvements

### 1. Dynamic Backend System (`server.py`)
*   **Centralized API**: Replaced static data with a Flask-based API that serves as the "brain" for navigation.
*   **KakaoMap Integration**: Implemented a **Dual-Layer Routing Engine** that uses **OSRM (Open Source Routing Machine)** by default for instant, key-free operation, while remaining fully compatible with the **Kakao Mobility API** for premium regional data.
*   **Emotion-Based Logic**: Developed a custom algorithm that adjusts routing priorities based on the driver's state:
    *   **Stressed/Angry**: Prioritizes the **fastest** route to reduce time on the road.
    *   **Calm**: Selects a **balanced/scenic** route for a pleasant drive.
    *   **Sleepy**: Focuses on **simplicity and safety** by prioritizing main roads.

### 2. Mobile App Connectivity (`mood_route_screen.dart`)
*   **Full-Stack Integration**: The mobile app is now fully connected to the ADAMS backend. It sends real-time location and destination data to the server and receives optimized route polylines.
*   **Realistic Mapping**: Implemented advanced coordinate parsing to render complex route geometries provided by the KakaoMap API directly on the Flutter map interface.
*   **User Experience**: Updated the UI to seamlessly transition between different "Mood Routes," providing visual feedback as the system syncs with the backend.

## Technical Stack
*   **Backend**: Python, Flask, Requests
*   **Frontend**: Flutter (Dart), Flutter Map, Dio
*   **APIs**: OSRM (Default Routing), Kakao Mobility API (Optional/Premium), OpenStreetMap (Tiles)

## Conclusion
This update successfully bridges the gap between driver monitoring and intelligent navigation, making ADAMS a more proactive and realistic safety assistant.
