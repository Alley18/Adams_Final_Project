import json
import time
from brain import AdamsBrain
from logger import log_event
from voice_engine import AdamsVoice
from ear_engine import AdamsEars

def serious_test():
    # 1. Initialize our components
    adams = AdamsBrain()
    voice = AdamsVoice()
    ears = AdamsEars()
    
    # 2. Define the scenarios to test
    live_stream = [
        "Eye openness: 95%, Emotion: Neutral, Gaze: Forward",
        "Eye openness: 5%, Yawning: YES, Duration: 3s",           # Sleepy Case
        "Eye openness: 85%, Emotion: High Anger, Gaze: Road",     # Road Rage Case
        "Eye openness: 90%, Emotion: Happy, Gaze: Road"           # Good Mood Case
    ]

    print("🚦 ADAMS COGNITIVE MONITORING STARTING...")
    print("="*50)
    
    # 3. Start the loop
    for detection in live_stream:
        # Get AI Logic
        raw_response = adams.generate_advice(detection)
        
        # Log the raw data to CSV
        log_event(detection, raw_response)
        
        try:
            # Parse the AI JSON response
            data = json.loads(raw_response)
            
            print(f"\n[DATA]: {detection}")
            print(f"[{data['level']}] {data['message']}")
            
            # --- VOICE OUTPUT ---
            voice.say(data['message'])

            # --- INTERACTIVE VOICE CHECK ---
            if data['level'] == "DANGER":
                voice.say("You look tired. Should I find a rest stop?")
                
                # Listen for driver response
                driver_answer = ears.listen()
                
                if "yes" in driver_answer.lower():
                    voice.say("Searching for the nearest rest area now.")
                elif "no" in driver_answer.lower():
                    voice.say("Okay, but please stay alert. I will keep monitoring.")

            # --- UI OUTPUT ---
            if 'suggested_route' in data:
                print(f"🗺️  ROUTE: {data['suggested_route']}")
            
            if data['buzzer_active']:
                print("🔊 !!! BUZZER ACTIVE !!!")
                
            # Test notification filtering
            notif = adams.filter_notifications(data['level'], "New Text: Where are you?")
            print(f"📱 {notif}")
            
            print("-" * 50)

            # Wait between cases so the voice can finish
            time.sleep(3)
            
        except Exception as e:
            print(f"Parsing Error: {e}")

if __name__ == "__main__":
    serious_test()