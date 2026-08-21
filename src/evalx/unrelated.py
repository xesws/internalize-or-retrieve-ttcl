"""Unrelated-probe pool (locality health check, proposal §5.2).

General-knowledge questions with NO connection to any workload memory; every
arm answers them at end-of-stream and is compared against the UNEDITED base
model on the same questions (drift = base hit-rate − arm hit-rate).
Frozen; changing it requires a new version + changelog.
"""
UNRELATED_POOL = [
    {"id": "uq01", "q": "What is the capital of Australia?", "keywords": ["canberra"]},
    {"id": "uq02", "q": "Who wrote the play Hamlet?", "keywords": ["shakespeare"]},
    {"id": "uq03", "q": "What is the chemical symbol for iron?", "keywords": ["fe"]},
    {"id": "uq04", "q": "In which country are the pyramids of Giza?", "keywords": ["egypt"]},
    {"id": "uq05", "q": "What planet is known as the red planet?", "keywords": ["mars"]},
    {"id": "uq06", "q": "How many continents are there?", "keywords": ["seven", "7"]},
    {"id": "uq07", "q": "What is the largest ocean on Earth?", "keywords": ["pacific"]},
    {"id": "uq08", "q": "Who painted the Mona Lisa?", "keywords": ["vinci", "leonardo"]},
    {"id": "uq09", "q": "What gas do plants absorb from the atmosphere?", "keywords": ["carbon dioxide", "co2"]},
    {"id": "uq10", "q": "What is the freezing point of water in Celsius?", "keywords": ["zero", "0"]},
    {"id": "uq11", "q": "Which instrument measures atmospheric pressure?", "keywords": ["barometer"]},
    {"id": "uq12", "q": "What is the longest river in Africa?", "keywords": ["nile", "congo"]},
    {"id": "uq13", "q": "In what year did the first human walk on the Moon?", "keywords": ["1969"]},
    {"id": "uq14", "q": "What is the primary language spoken in Brazil?", "keywords": ["portuguese"]},
    {"id": "uq15", "q": "Which metal is liquid at room temperature?", "keywords": ["mercury"]},
]
