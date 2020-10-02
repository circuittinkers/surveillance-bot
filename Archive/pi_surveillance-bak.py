from pyimagetemp.tempimage import TempImage
from picamera.array import PiRGBArray
from picamera import PiCamera
import argparse
import warnings
import datetime
import imutils
import json
import time
import cv2
from subprocess import Popen, PIPE

# construct the arg. parser and parse the args
ap = argparse.ArgumentParser()
ap.add_argument("--c", "--conf", required=True,
	help="path to the JSON configuration file")
ap.add_argument("--s", "--subs", required=True,
	help="path to the JSON subscribers list file")
args = vars(ap.parse_args())

# filter warnings, load the configuration and init the Telegram
warnings.filterwarnings("ignore")
conf = json.load(open(args["c"]))

client = None
#extProc = Popen(["python","telegram-run.py","--conf", args["c"], "--subs",
#	args["s"]],stdin=PIPE,stdout=PIPE)

#if extProc.poll() is None:
#	print("Telegram Bot Status: Online")

# check to see if dropbox should be used
if conf["use_dropbox"]:
	# connect to telegram bot and start the session auth process
	pass

# init the camera and grab a reference to the raw camera capture
camera = PiCamera()
camera.resolution = tuple(conf["resolution"])
camera.framerate = conf["fps"]
rawCapture = PiRGBArray(camera, size=tuple(conf["resolution"]))

# allow the camera to warm up, then init the average frame, last
# uploaded timestamp, and frame motion counter
print("[INFO] Warming up...")
time.sleep(conf["camera_warmup_time"])
avg = None
lastUploaded = datetime.datetime.now()
motionCounter = 0

# capture frames from the camera
for f in camera.capture_continuous(rawCapture, format="bgr", use_video_port=True):
	# grab the raw NumPy array representing the image and init
	# the timestamp and occupied/unoccupied text
	frame = f.array
	timestamp = datetime.datetime.now()
	text = "Unoccupied"

	# resize the frame, convert it to grayscale, and blur it
	frame = imutils.resize(frame, width=500)
	gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
	gray = cv2.GaussianBlur(gray, (21, 21), 0)

	# if the average frame is none, init it
	if avg is None:
		print("[INFO] starting background model...")
		avg = gray.copy().astype("float")
		rawCapture.truncate(0)
		continue

	# accumulate the weighted average between the current frame and
	# previous frames, then compute the differences between the current
	# frame and running average
	cv2.accumulateWeighted(gray, avg, 0.5)
	frameDelta = cv2.absdiff(gray, cv2.convertScaleAbs(avg))

	# threshold the delta image, dilate the thresholded image to fill
	# in the holes then find contours on thresholded image
	thresh = cv2.threshold(frameDelta, conf["delta_thresh"], 255,
		cv2.THRESH_BINARY)[1]
	thresh = cv2.dilate(thresh,None, iterations=2)
	cnts = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL,
		cv2.CHAIN_APPROX_SIMPLE)
	cnts = imutils.grab_contours(cnts)

	# loop over contours
	for c in cnts:
		# if the contour is too small, ignore
		if cv2.contourArea(c) < conf["min_area"]:
			continue

		# compute the bounding box for the contour, draw it on the
		# frame, and then update the text
		(x, y, w, h) = cv2.boundingRect(c)
		cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
		text = "Occupied"

	# draw the text and timestamp on the frame
	ts = timestamp.strftime("%A %d %B %Y %I:%M:%S%p")
	cv2.putText(frame, "Status: {}".format(text), (10,20),
		cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
	cv2.putText(frame, ts, (10, frame.shape[0] - 10),
		cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 255), 1)

	# check to see if the room is occupied
	if text == "Occupied":
		# check to see if enough time has passed between uploads
		if (timestamp - lastUploaded).seconds >= conf["min_upload_seconds"]:
			# increment the motion counter
			motionCounter +=1

		# check to see if the number of frames with consistent motion
		# is high enough
		if motionCounter >= conf["min_motion_frames"]:
			# check to see if telegram should be used
			with open(args['s'],'r') as f:
				subs = json.load(f)
			if "subscribers" in subs:
				for key in subs['subscribers']:
					if key['user_name'] == 'name':
						pass
					else:
						print("Uploading to {}".format(key['user_name']))
			if conf["use_dropbox"]:
				# write the image to temp file
				t = TempImage()
				cv2.imwrite(t.path, frame)

				# upload the image to Telegram
				# then clear the temp file
				print("[UPLOADING] {}".format(ts))
				# source for telegram upload

				t.cleanup()

			# update the last uploaded timestamp
			# and reset motion counter
			lastUploaded = timestamp
			motionCounter = 0

	# otherwise, the room is not occcupied
	else:
		motionCounter = 0

	# check to see if the frames should be displayed to screen
	if conf["show_video"]:
		# display the video feed
		cv2.imshow("Security Feed", frame)
		key = cv2.waitKey(1) & 0xFF

		# if the 'q' key is pressed, break from the loop
		if key == ord("q"):
			print("[EXITING] Terminating other process...")
			extProc.terminate()
			time.sleep(10)
			if extProc.poll() is not None:
				print("Telegram Bot Status: Offline")
			break

	# clear the stream in prepration for the next frame
	rawCapture.truncate(0)
