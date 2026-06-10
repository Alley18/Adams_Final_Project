# ADAMS: Advanced Driver Alertness Monitoring System

## First Draft Project Documentation

**Project Name:** ADAMS  
**Full Name:** Advanced Driver Alertness Monitoring System  
**Project Type:** AI driver safety assistant / intelligent co-pilot prototype  
**Main Technologies:** Python, OpenCV, DeepFace, FastAPI, Flutter, Firebase, Raspberry Pi GPIO, Groq LLM API  

## Table of Contents

1. [Abstract](#abstract)
2. [Project Overview](#project-overview)
3. [Problem Statement](#problem-statement)
4. [Project Objectives](#project-objectives)
5. [Scope of the Project](#scope-of-the-project)
6. [Target Users](#target-users)
7. [Core System Features](#core-system-features)
8. [System Architecture](#system-architecture)
9. [Module Breakdown](#module-breakdown)
10. [Data Flow](#data-flow)
11. [AI and Decision-Making Logic](#ai-and-decision-making-logic)
12. [Mobile Application](#mobile-application)
13. [Backend API](#backend-api)
14. [Hardware and Edge Components](#hardware-and-edge-components)
15. [Data Logging and Analytics](#data-logging-and-analytics)
16. [User Interaction Flow](#user-interaction-flow)
17. [Technologies Used](#technologies-used)
18. [Project Directory Structure](#project-directory-structure)
19. [Installation and Running Guide](#installation-and-running-guide)
20. [Testing and Demonstration Plan](#testing-and-demonstration-plan)
21. [Current Status](#current-status)
22. [Limitations](#limitations)
23. [Major Demonstration Upgrade](#major-demonstration-upgrade)
24. [Conclusion](#conclusion)

## Abstract

ADAMS is an AI-powered driver safety assistant that monitors a driver's alertness, attention, and emotional condition in real time. The system is designed to detect unsafe driving states such as drowsiness, distraction, stress, anger, and hands-off-wheel behavior. When risk is detected, ADAMS responds through voice alerts, mobile warnings, buzzer or vibration feedback, route recommendations, and backend event logging.

The project combines computer vision, artificial intelligence, mobile application development, backend APIs, live database communication, and physical hardware alerts. Instead of functioning as a simple drowsiness detector, ADAMS acts as an intelligent in-car co-pilot that can observe driver behavior, reason about risk, communicate with the driver, and record safety events for later review.

This documentation describes the purpose, design, architecture, features, current implementation, and future direction of the ADAMS project.

## Project Overview

ADAMS stands for **Advanced Driver Alertness Monitoring System**. It is built as a complete driver-assistance prototype with multiple connected components:

- A camera-based vision pipeline that monitors the driver's face and eyes.
- An AI safety controller that decides the seriousness of the current driver state.
- A voice assistant that speaks alerts and supports basic driver conversation.
- A backend server that stores and serves driver safety data.
- A mobile app that displays live driver status, route options, guardian alerts, and analytics.
- Optional Raspberry Pi and hardware components for buzzer, sensor, and edge-device support.

The system is intended to show how a modern driver safety assistant can go beyond basic detection. ADAMS does not only recognize a dangerous state; it also responds in a way that is visible, audible, and useful to the driver.

## Problem Statement

Driver fatigue and distraction are serious causes of road accidents. A driver may become sleepy, emotionally stressed, distracted by surroundings, or unaware that their attention is decreasing. Traditional warning systems often depend on simple rules or single signals, such as lane deviation or eye closure.

However, real driver risk is usually multi-factor. A driver may be slightly tired, emotionally stressed, looking away from the road, or interacting with a phone. These separate signals become more dangerous when they happen together.

The problem ADAMS addresses is:

> How can an intelligent system monitor multiple driver safety signals in real time and respond before the situation becomes dangerous?

ADAMS attempts to solve this by combining computer vision, emotion recognition, AI decision-making, voice feedback, mobile monitoring, and safety analytics.

## Project Objectives

The main objectives of ADAMS are:

1. Detect driver drowsiness using eye and facial monitoring.
2. Detect driver distraction using gaze or attention-related signals.
3. Identify emotional states such as stress, anger, tiredness, happiness, or neutrality.
4. Generate appropriate safety warnings based on driver telemetry.
5. Provide voice-based alerts so the driver does not need to look away from the road.
6. Display live safety status through a mobile application.
7. Store safety events for analytics and post-trip review.
8. Recommend route behavior based on driver mood and risk level.
9. Support hardware-based safety alerts such as buzzer or vibration.
10. Provide a foundation for future emergency escalation features.

## Scope of the Project

### Included in Scope

The current version of ADAMS includes:

- Real-time camera monitoring.
- Eye openness and drowsiness detection.
- Distraction detection logic.
- Emotion detection using facial analysis.
- AI-generated safety advice.
- Voice alert output.
- Conversational assistant behavior.
- Mobile app dashboard.
- Guardian safety display.
- Mood-based route screen.
- Backend API for driver state, alerts, analytics, sessions, and logs.
- CSV-based event logging.
- Firebase integration for live mobile updates.
- Raspberry Pi and hardware support files.

### Outside Current Scope

The current version does not fully implement:

- Real vehicle control.
- Automatic braking or steering.
- Real emergency service calling.
- Production-grade driver identification.
- Certified medical or automotive safety validation.
- Commercial vehicle integration such as CAN bus access.

ADAMS is a prototype and academic project, not a certified vehicle safety product.

## Target Users

ADAMS is designed for:

- Drivers who may experience fatigue or distraction.
- Long-distance drivers.
- Student drivers or training environments.
- Fleet-monitoring research prototypes.
- Academic demonstrations of AI safety systems.
- Developers studying human-centered AI and driver assistance.

## Core System Features

### 1. Driver Drowsiness Detection

ADAMS monitors the driver's eye openness and detects when the eyes appear closed or nearly closed for a dangerous amount of time.

The system uses a threshold-based interpretation of eye-opening values. If the eye openness value falls below the configured threshold, ADAMS classifies the driver's eye state as closed. When the closed-eye or drowsy condition continues long enough, the system triggers a warning.

Example:

1. The camera captures the driver's face.
2. Eye openness is calculated.
3. The value remains low for several seconds.
4. ADAMS classifies the driver as drowsy.
5. A voice alert warns the driver.
6. The event is logged for analytics.

### 2. Driver Distraction Detection

ADAMS can detect attention loss or distraction when the driver's gaze is not focused forward for too long. This feature is important because a driver can be fully awake but still unsafe if they repeatedly look away from the road.

Example warning:

> "Eyes on the road!"

This warning is intentionally short because the driver should not receive long spoken messages while driving.

### 3. Emotion-Aware Monitoring

The system uses facial emotion recognition to estimate the driver's emotional condition. Detected emotions are mapped into safer driving categories:

| Raw Emotion | ADAMS Category |
| --- | --- |
| Angry | Angry |
| Disgust | Angry |
| Fear | Stressed |
| Sad | Stressed |
| Happy | Happy |
| Surprise | Neutral |
| Neutral | Neutral |

Emotion-aware monitoring allows ADAMS to respond with better context. For example, a stressed driver may receive a calming message or a less stressful route recommendation.

### 4. AI Safety Controller

The AI safety controller receives driver telemetry and returns a structured safety decision. The decision includes:

- Safety level.
- Spoken warning message.
- Whether a buzzer should activate.
- Suggested route type.

The safety levels are:

| Level | Meaning |
| --- | --- |
| `INFO` | Normal or low-risk state. |
| `WARNING` | Unsafe condition detected but not immediately critical. |
| `DANGER` | High-risk driver state requiring urgent attention. |
| `ERROR` | AI or system component failure. |

### 5. Voice Alert System

ADAMS uses voice output to warn the driver without requiring visual attention. This is important because visual dashboard warnings can distract the driver further.

Voice alerts are short, direct, and safety-focused. Examples include:

- "Wake up! Focus on the road."
- "Eyes on the road!"
- "Please stay focused."

The voice system supports priority alerts so urgent warnings can interrupt lower-priority spoken responses.

### 6. Conversational Co-Pilot

ADAMS includes a conversational mode where the driver can speak to the assistant. The assistant is designed to answer briefly and naturally.

This feature supports a more realistic in-car experience. The driver can ask simple questions while ADAMS continues to monitor safety context.

The system separates:

- **Driving Mode:** Primary focus is safety monitoring.
- **Conversation Mode:** Driver can speak with ADAMS.

### 7. Guardian Safety Mode

Guardian mode is a mobile app feature that displays immediate driver safety status. It can show whether the driver is normal, in danger, or needs correction.

Guardian mode can:

- Display the current driver state.
- Display hands-on-wheel status.
- Change the screen background during danger.
- Trigger vibration or haptic feedback.
- Speak a warning using mobile text-to-speech.

### 8. Mood-Based Route Recommendation

The route system connects driver emotion with navigation behavior. Instead of treating all routes the same, ADAMS can recommend route styles based on driver mood.

Example route types:

| Mood | Route Behavior |
| --- | --- |
| Relaxed | Scenic or calm route. |
| Happy | Lively route with points of interest. |
| Stressed | Fastest or simplest route. |
| Tired | Safer route with rest-friendly behavior. |
| Focused | Efficient route. |
| Neutral | Balanced route. |

If the driver's emotional state changes during a trip, ADAMS can update the route selection.

### 9. Mobile Safety Dashboard

The mobile application provides a visible interface for monitoring and demonstration. It includes:

- Live co-pilot screen.
- Guardian warning screen.
- Mood-based route screen.
- Analytics screen.

This makes the system easier to present because the professor can clearly see driver state, alerts, risk, and route behavior.

### 10. Backend Analytics

The backend converts driver events into structured analytics. It can calculate:

- Total events.
- Danger count.
- Warning count.
- Info count.
- Drowsy count.
- Distracted count.
- Buzzer activations.
- Latest risk score.
- Highest risk score.
- State breakdown.
- Recent timeline.
- Safety recommendations.

This gives the project a data-analysis layer, not only a live detection layer.

## System Architecture

ADAMS uses a multi-layer architecture:

```text
                         +----------------------+
                         |      Mobile App      |
                         | Flutter + Firebase   |
                         +----------+-----------+
                                    |
                                    |
                         +----------v-----------+
                         |      Backend API     |
                         | FastAPI + CSV Logs   |
                         +----------+-----------+
                                    |
          +-------------------------+-------------------------+
          |                                                   |
+---------v----------+                             +----------v---------+
|  Vision Pipeline   |                             |   AI Engine        |
| OpenCV + DeepFace  |                             | Safety + Chat      |
+---------+----------+                             +----------+---------+
          |                                                   |
          |                                                   |
+---------v----------+                             +----------v---------+
| Camera / Sensors   |                             | Voice / Alerts     |
| Face, eyes, wheel  |                             | Speech + Buzzer    |
+--------------------+                             +--------------------+
```

The system is divided into four major layers:

1. **Sensing Layer:** Camera, eye detection, emotion detection, hardware sensors.
2. **Intelligence Layer:** AI safety controller and conversational assistant.
3. **Communication Layer:** Backend API, Firebase, logs, WebSocket support.
4. **User Interface Layer:** Mobile app, voice alerts, buzzer/haptic feedback.

## Module Breakdown

### Main Vision Pipeline

File:

- `main_controller.py`

Responsibilities:

- Open the camera.
- Capture live frames.
- Run eye and face analysis.
- Detect drowsiness and distraction.
- Run emotion detection at intervals.
- Manage driving mode and conversation mode.
- Trigger voice alerts.
- Trigger AI-generated safety responses.
- Display camera overlay and driver status.

### Stream Integration

File:

- `ml/stream_data.py`

Responsibilities:

- Define telemetry data models.
- Convert raw telemetry into backend payloads.
- Send driver status to the backend API.
- Provide a smoke-test entry point for backend communication.

### AI Engine

Folder:

- `ai_engine/`

Important files:

- `brain.py`
- `adams_voice.py`
- `adams_ears.py`
- `adams_route.py`

Responsibilities:

- Generate structured safety advice.
- Provide conversational assistant responses.
- Manage spoken voice output.
- Listen for driver speech.
- Provide route-related advice.

### Backend

Folder:

- `backend/`

Important files:

- `backend/server.py`
- `backend/models/schemas.py`
- `backend/services/log_reader.py`
- `backend/core/config.py`

Responsibilities:

- Serve current driver state.
- Serve alert history.
- Serve safety analytics.
- Serve session summaries.
- Normalize log data.
- Accept manual test events.
- Export event data as CSV.
- Provide live WebSocket state updates.

### Mobile Application

Folder:

- `mobile_app/`

Important files:

- `mobile_app/lib/main.dart`
- `mobile_app/lib/screens/co_pilot_screen.dart`
- `mobile_app/lib/screens/guardian_screen.dart`
- `mobile_app/lib/screens/mood_route_screen.dart`
- `mobile_app/lib/screens/analytics_screen.dart`

Responsibilities:

- Display live safety state.
- Show Guardian mode warnings.
- Display mood-based route options.
- Show analytics and insights.
- Trigger vibration and text-to-speech warnings.
- Connect to Firebase and backend services.

### Hardware and Edge Support

Folders:

- `hardware/`
- `pi_edge/`

Responsibilities:

- Buzzer control.
- GPIO testing.
- Sensor input testing.
- Raspberry Pi edge logging.
- Cloud synchronization support.

## Data Flow

The basic ADAMS data flow is:

```text
Camera / Sensors
      |
      v
Vision Pipeline
      |
      v
Driver Telemetry
      |
      +----> AI Safety Controller ----> Voice Alert / Route Suggestion
      |
      +----> Backend API -------------> Logs / Analytics / Sessions
      |
      +----> Firebase ----------------> Mobile App Live Status
```

Detailed flow:

1. The camera captures the driver's face.
2. The vision pipeline analyzes the frame.
3. Eye openness, drowsiness, distraction, and emotion are extracted.
4. ADAMS builds a telemetry snapshot.
5. The AI engine decides the safety level and recommended action.
6. Voice or buzzer alerts are triggered if needed.
7. Driver state is sent to the backend and/or Firebase.
8. The mobile app displays the current driver state.
9. Logs are stored for analytics and trip review.

## AI and Decision-Making Logic

ADAMS uses a combination of rule-based detection and AI-based response generation.

### Rule-Based Detection

Rule-based logic is used for immediate safety decisions such as:

- Eye openness below threshold.
- Drowsiness duration above threshold.
- Distraction duration above threshold.
- Cooldown periods between repeated alerts.
- Conversation mode blocking unnecessary interruptions.

These rules are important because safety-critical behavior should be predictable and fast.

### AI-Based Safety Advice

The AI engine uses driver telemetry to generate a structured response. The response format includes:

```json
{
  "level": "DANGER",
  "message": "Please pull over safely.",
  "buzzer_active": true,
  "suggested_route": "REST_STOP"
}
```

This allows ADAMS to combine fixed safety rules with more natural and context-aware driver communication.

## Mobile Application

The ADAMS mobile app is built with Flutter and uses a dark safety-dashboard interface.

### Co-Pilot Screen

The Co-Pilot screen represents the intelligent assistant side of ADAMS. It is intended for voice interaction and safety support.

### Guardian Screen

The Guardian screen displays urgent driver safety status. It reads live driver information and changes its visual state when danger is detected.

Guardian can show:

- Driver status.
- Hands-on-wheel status.
- Alert status.
- Full warning color state.
- Voice and vibration alerts.

### Mood Route Screen

The Mood Route screen connects emotion detection to navigation. It allows route styles to change based on driver mood.

It supports:

- Destination search.
- Route display.
- Multiple route moods.
- Auto-rerouting when emotion changes.
- Animated route progress for demonstration.

### Analytics Screen

The Analytics screen presents safety data visually. It includes:

- Session counts.
- Mood score.
- Risk hours.
- State distribution.
- Danger index.
- State transitions.
- AI insight cards.

## Backend API

The backend is built using FastAPI. It provides both legacy endpoints and versioned API endpoints.

### Important Endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Check backend health. |
| `GET /state` | Get latest driver state. |
| `GET /alerts` | Get recent safety alerts. |
| `GET /schema` | Get backend schema information. |
| `GET /api/v1/config` | Get backend configuration. |
| `GET /api/v1/analytics` | Get safety analytics summary. |
| `GET /api/v1/sessions` | Get trip/session summaries. |
| `GET /api/v1/conversation` | Get assistant conversation history. |
| `POST /api/v1/events` | Create a manual or test event. |
| `GET /api/v1/export/events.csv` | Export normalized event logs. |
| `WS /ws/state` | Stream live state and analytics. |

### Backend Data Model

A normalized driver event includes:

- Timestamp.
- Input text or telemetry source.
- Safety level.
- Message.
- Spoken text.
- Buzzer state.
- Driver state.
- Trigger.
- Suggested route.
- Recommended action.
- Session ID.
- Risk score.
- Event ID.

## Hardware and Edge Components

ADAMS includes hardware-related code for Raspberry Pi and physical alert devices.

Possible hardware features include:

- Buzzer activation.
- Force sensor or steering wheel sensor input.
- Raspberry Pi edge processing.
- Local trip logging.
- Cloud synchronization.

These components help show that ADAMS is not only a software dashboard but can also connect to physical safety devices.

## Data Logging and Analytics

ADAMS records events into CSV logs. The backend reads and normalizes these logs to produce analytics.

### Logged Event Examples

An event may represent:

- Drowsiness warning.
- Distraction warning.
- Emotion-based alert.
- Buzzer activation.
- Manual test event.
- Route recommendation.
- Conversation turn.

### Risk Score

The backend calculates a risk score from:

- Safety level.
- Buzzer activation.
- Driver state.
- Trigger type.

Higher scores indicate more dangerous situations.

## User Interaction Flow

### Normal Driving

1. Driver starts the system.
2. ADAMS begins camera monitoring.
3. Mobile app shows normal state.
4. Events are logged as normal or informational.

### Drowsiness Event

1. Driver's eyes remain closed.
2. ADAMS detects drowsiness.
3. ADAMS warns the driver using voice.
4. Backend records a danger or warning event.
5. Mobile app updates state and analytics.

### Distraction Event

1. Driver looks away for too long.
2. ADAMS detects distraction.
3. Voice alert tells the driver to focus on the road.
4. Guardian screen may show warning status.
5. Event is logged.

### Emotion-Based Route Update

1. Driver emotion changes.
2. ADAMS identifies the new dominant emotion.
3. Mood Route screen selects a safer or more suitable route style.
4. App shows route update message.

## Technologies Used

| Technology | Purpose |
| --- | --- |
| Python | Vision pipeline, AI engine, backend logic. |
| OpenCV | Camera capture and frame processing. |
| DeepFace | Emotion recognition. |
| FastAPI | REST API and WebSocket backend. |
| Pydantic | API data validation and models. |
| Flutter | Mobile application interface. |
| Dart | Mobile app programming language. |
| Firebase Realtime Database | Live driver state updates. |
| Groq LLM API | AI safety advice and assistant responses. |
| Raspberry Pi GPIO | Physical alert and sensor support. |
| CSV | Event logging and analytics storage. |

## Project Directory Structure

```text
Adams_Final_Project/
|
|-- ai_engine/
|   |-- brain.py
|   |-- adams_voice.py
|   |-- adams_ears.py
|   |-- adams_route.py
|
|-- backend/
|   |-- server.py
|   |-- api/
|   |-- core/
|   |-- models/
|   |-- services/
|
|-- hardware/
|   |-- alarm_control.py
|   |-- test.py
|
|-- logs/
|
|-- ml/
|   |-- stream_data.py
|
|-- mobile_app/
|   |-- lib/
|       |-- main.dart
|       |-- screens/
|       |-- services/
|       |-- widgets/
|
|-- navigation/
|
|-- pi_edge/
|
|-- shared/
|   |-- schema.json
|
|-- main_controller.py
|-- requirements.txt
|-- README.md
```

## Installation and Running Guide

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables

The AI engine requires a Groq API key:

```bash
GROQ_API_KEY=your_api_key_here
```

Depending on the setup, Firebase and route server configuration may also be required.

### 3. Run the Backend

```bash
uvicorn backend.server:app --host 0.0.0.0 --port 8000 --reload
```

Backend documentation is available at:

```text
http://127.0.0.1:8000/docs
```

### 4. Run the Main Vision Pipeline

```bash
python main_controller.py
```

This starts camera monitoring, emotion detection, alert logic, and voice interaction.

### 5. Run the Mobile App

```bash
cd mobile_app
flutter pub get
flutter run
```

When testing on a physical phone, the backend URL should use the computer or Raspberry Pi IP address instead of `127.0.0.1`.

## Testing and Demonstration Plan

The project can be demonstrated through the following scenarios.

### Scenario 1: Normal Driver

Expected result:

- Driver state remains normal.
- Mobile dashboard shows safe status.
- No urgent alert is triggered.

### Scenario 2: Drowsy Driver

Expected result:

- Eye openness decreases.
- ADAMS detects drowsiness.
- Voice alert is triggered.
- Event appears in backend logs and analytics.

### Scenario 3: Distracted Driver

Expected result:

- Driver looks away.
- ADAMS detects distraction.
- Voice warning tells driver to focus.
- Guardian screen displays warning state.

### Scenario 4: Stressed or Angry Driver

Expected result:

- Emotion detection identifies high-risk emotion.
- AI generates a calmer safety response.
- Mood Route may suggest a safer route type.

### Scenario 5: Mobile Guardian Warning

Expected result:

- Mobile app displays danger state.
- Vibration or haptic alert is triggered.
- Text-to-speech warning is spoken.

### Scenario 6: Backend Analytics

Expected result:

- Events are counted.
- Risk scores are calculated.
- Analytics screen shows safety insights.

## Current Status

The current project includes:

- Working project structure.
- Vision pipeline logic.
- Eye and distraction monitoring.
- Emotion detection integration.
- AI safety controller.
- Voice output.
- Conversational assistant mode.
- Backend API.
- Mobile app screens.
- Guardian safety mode.
- Emergency Co-Pilot demonstration mode with countdown and simulated escalation.
- Mood route screen.
- Analytics dashboard.
- Event logging.
- Raspberry Pi and hardware support files.

## Limitations

Current limitations include:

- The system depends on camera quality and lighting.
- Emotion detection may not always be accurate.
- Some hardware features require Raspberry Pi or physical devices.
- Route behavior may depend on external services or mock fallback routes.
- The system is a prototype and not certified for real vehicle safety use.
- Emergency escalation is implemented as a safe demonstration mode, not as a real emergency-calling service.
- Real-world testing is limited compared to production automotive systems.

## Major Demonstration Upgrade

The major demonstration upgrade is **Emergency Co-Pilot Mode**.

This mode makes ADAMS more visible and more advanced during demonstration. Instead of only warning the driver, ADAMS starts an escalation workflow when serious danger is detected.

### Emergency Co-Pilot Mode Concept

When ADAMS detects a high-risk situation such as prolonged drowsiness, distraction, or unresponsiveness:

1. The mobile app switches into a full-screen emergency warning mode.
2. The phone vibrates and plays a warning.
3. ADAMS speaks an urgent voice prompt.
4. A countdown appears on the screen.
5. The driver must press an "I'm OK" button to cancel escalation.
6. If the driver does not respond, ADAMS logs an emergency incident.
7. The system displays a simulated emergency contact call for demonstration.

For safety and legal reasons, the prototype does not automatically call a real emergency number. It uses a simulated emergency escalation screen and logs the incident. This allows the feature to be demonstrated clearly without risking accidental emergency calls.

### Trigger Strategy

The emergency mode is intentionally conservative because driver detection can sometimes be noisy. ADAMS does not trigger emergency mode from a single random detection. It waits for a sustained severe condition, such as:

- Drowsy, sleeping, or unresponsive state held for 30 seconds.
- Critical danger level.
- Hands off the wheel while the driver state is abnormal.

For class presentation, the mobile app also includes a visible emergency demo button. This button lets the presenter trigger Emergency Co-Pilot Mode instantly without waiting for unreliable live detection.

### Why This Upgrade Is Important

This feature changes ADAMS from a passive monitoring system into an active safety intervention prototype. It gives the project a strong visual demonstration and shows how the system could help prevent accidents before they happen.

## Conclusion

ADAMS is an intelligent driver alertness monitoring system that combines real-time driver observation, AI decision-making, voice interaction, mobile safety display, route support, analytics, and hardware alerts.

The project is designed to demonstrate a complete driver safety assistant rather than a single-purpose drowsiness detector. By combining multiple technologies into one system, ADAMS shows how artificial intelligence can be used for real-time safety monitoring and accident-prevention support.

With Emergency Co-Pilot Mode, the system becomes a stronger prototype by adding a clear emergency escalation workflow that is both practical and easy to demonstrate.
