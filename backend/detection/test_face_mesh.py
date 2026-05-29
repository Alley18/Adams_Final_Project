import cv2
import mediapipe as mp
import numpy as np
import sys
import os

# Ensure the root directory is in the path so we can import 'backend'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from backend.detection.face_mesh import EyeDetector

def run_test():
    print("--- ADAMS Face Mesh Diagnostic Tool ---")
    
    # 1. Check for Model File
    # The EyeDetector looks for 'face_landmarker.task' in its own directory
    model_check = os.path.join(os.path.dirname(__file__), "face_landmarker.task")
    if not os.path.exists(model_check):
        print(f"ERROR: Model file not found at {model_check}")
        print("Please download it and place it in the backend/detection/ folder.")
        return

    try:
        print("Initializing AI Brain (EyeDetector)...")
        detector = EyeDetector()
        
        print("Opening Camera (using DirectShow for Windows)...")
        # Try index 0. If it fails, try 1 or 2.
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

        if not cap.isOpened():
            print("ERROR: Could not open camera. Check privacy settings or if another app is using it.")
            return

        # Set resolution for better performance
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        print("System Online. Press 'q' to quit.")

        while cap.isOpened():
            success, frame = cap.read()
            if not success:
                print("Warning: Failed to grab frame from camera.")
                break

            # Run the ADAMS analysis logic
            results = detector.analyze(frame)
            
            # Generate the HUD overlay
            annotated_frame = detector.draw_overlay(frame, results)

            # Show the results
            cv2.imshow("ADAMS Vision Node - Test Mode", annotated_frame)
            
            # Print metrics to terminal for debugging
            if results["face_detected"]:
                print(f"EAR: {results['ear_value']:.2f} | Yaw: {results['yaw_deg']:.1f}° | Drowsy: {results['is_drowsy']}", end='\r')
            else:
                print("Searching for face...", end='\r')

            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("\nUser requested exit.")
                break

    except Exception as e:
        print(f"\nCRITICAL ERROR: {e}")

    finally:
        if 'cap' in locals():
            cap.release()
        cv2.destroyAllWindows()
        print("\nCleanup complete. Vision Node shut down.")

if __name__ == "__main__":
    run_test()