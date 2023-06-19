from flask import Flask, render_template

app = Flask(__name__)

class GuiReplayer:
    def __init__(self, hand_data):
        self.hand_data = hand_data

    def render_hand_replay(self):
        # Access the hand data object and populate the HTML elements with relevant information
        # Example: Add hand details to the hand replay
        hand_details = f"Hand No: {self.hand_data['HAND NO.']}"

        # Render the hand replay template with the hand details
        return render_template('hand_replay.html', hand_details=hand_details)

@app.route('/')
def hand_replay():
    # Replace `hand_data` with the actual hand data you have
    hand_data = {
        # Hand data object
    }

    replayer = GuiReplayer(hand_data)
    hand_replay_html = replayer.render_hand_replay()
    return render_template('index.html', hand_replay=hand_replay_html)

if __name__ == '__main__':
    app.run()
