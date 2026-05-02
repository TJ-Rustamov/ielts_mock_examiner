import os
import sys

# Add the backend directory to the path so we can import from ai_services
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ai_services.tts_client import KokoroClient

def main():
    static_audio_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static_audio")
    os.makedirs(static_audio_dir, exist_ok=True)

    client = KokoroClient()
    
    phrases = {
        "greeting.wav": "Hi. I am your AI mock IELTS examiner and I will be conducting your test. To start could you please tell me about yourself?",
        "greeting_part1.wav": "Good day. I am your AI mock IELTS examiner for today. We will now conduct Part 1 of the speaking test. Could you please tell me your full name?",
        "greeting_part2.wav": "Good day. I am your AI mock IELTS examiner for today. We will now conduct Part 2 of the speaking test. Let's begin.",
        "greeting_part3.wav": "Good day. I am your AI mock IELTS examiner for today. We will now begin Part 3 of the speaking test.",
        "prep_instructions.wav": "You will have 1 minute to prepare your answer, and then you will have 1 to 2 minutes to speak. Your preparation time starts now.",
        "prep_time_up.wav": "Alright, your time is up. You can start speaking now.",
        "move_to_part2.wav": "Now, let's move on to Part 2 of the test.",
        "move_to_part3.wav": "I see. Then let's move on to Part 3.",
        "farewell.wav": "Thank you, that is the end of the speaking test.",
        "next_topic.wav": "Alright, let's move on to the next topic.",
    }

    print(f"Generating static audio files in {static_audio_dir}...")
    
    for filename, text in phrases.items():
        filepath = os.path.join(static_audio_dir, filename)
        print(f"Generating {filename}...")
        
        # Using KokoroClient to generate the audio
        audio_bytes = client.generate_audio(text)
        
        with open(filepath, "wb") as f:
            f.write(audio_bytes)
            
        print(f"Saved {filename} ({len(audio_bytes)} bytes)")

if __name__ == "__main__":
    main()
