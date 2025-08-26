# galactic-flight-tracker
Code to run on a Pimoroni Galactic Unicorn led matrix to track flights nearby using the OpenSky api.

You need to set your wifi details, location coordinates, and opensky credentials in secrets.py.

A free opensky account gives you 4000 credits a day which let's you query every 15 seconds for 16 hours a day. The display goes in to 'night mode' from 00:00 to 08:00 and requests are not made. 