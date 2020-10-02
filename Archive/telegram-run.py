import RPi.GPIO as GPIO
import threading
import emoji
import json
from telegram.ext import CommandHandler, Updater, MessageHandler, Filters
import time
import datetime
import argparse
import warnings

from pyimagetemp.tempimage import TempImage
from picamera.array import PiRGBArray
from picamera import PiCamera
import imutils
import cv2

cmd_ls = "1) /start "+emoji.emojize(':key:')+"\n 2) /stop\n 3) /help "+emoji.emojize(':warning:')+"\n 4) /subscribe "+emoji.emojize(':memo:')+"\n 5) /unsubscribe "+emoji.emojize(':electric_plug:')+"\n 6) /alarm "+emoji.emojize(':bell:')

alarm_status = None

# construct arg parser
ap = argparse.ArgumentParser()
ap.add_argument("-c", "--conf", required=True,
	help="path to JSON configuration file")
ap.add_argument("-s", "--subs", required=True,
	help="path to JSON subscriber list file")
args = vars(ap.parse_args())

# filter warning and load config
warnings.filterwarnings("ignore")
conf = json.load(open(args["conf"]))

client = Updater(token=conf["telegram_access_token"], use_context=True)

# init the GPIO
try:
	GPIO.setmode(GPIO.BCM)
	RELAY_1_GPIO = conf["relay-0"]
	GPIO.setup(RELAY_1_GPIO, GPIO.OUT) # Assign Mode
	GPIO.output(RELAY_1_GPIO, GPIO.LOW)
	alarm_status = False
except:
	print("GPIO init failed.")

def start(update, context):
	context.bot.send_message(chat_id= update.effective_chat.id,
		text="Hi, Welcome to Surveillance Alert Bot! /help for help.")

def unknown(update, context):
	context.bot.send_message(chat_id= update.effective_chat.id,
		text="Sorry, I didn't understand that. / Saya tidak faham")

def stop(update, context):
	context.bot.send_message(chat_id = update.effective_chat.id,
		text="Halting my internal process... Goodbye!")
	threading.Thread(target=shutdown).start()

def shutdown():
	client.stop()
	client.is_idle = False

def help(update, context):
	context.bot.send_message(chat_id= update.effective_chat.id,
		text="Available Commands:\n{}".format(cmd_ls))

def alarm(update, context):
	global alarm_status
	# check alarm status, if enabled, disabled it and vice versa	
	if alarm_status:
		context.bot.send_message(chat_id= update.effective_chat.id,
				text="Alarm has been turned off. /alarm to re-enable.")
		GPIO.output(RELAY_1_GPIO,GPIO.HIGH)		
	else:
		context.bot.send_message(chat_id= update.effective_chat.id,
			text="Triggering alarm... /alarm to disable.")
		alarm_status= True
		GPIO.output(RELAY_1_GPIO,GPIO.HIGH)

def subscribe(update, context):
	# check if user id exist
	user_id = update.effective_user.id
	exist = False
	present = False
	with open(args["subs"],'r') as f:
		subs = json.load(f)
	print("Current subs - {}".format(subs))
	if "subscribers" in subs:
		exist = True
		for s in subs["subscribers"]:
			if user_id in s.values():
				context.bot.send_message(chat_id= update.effective_chat.id,
					text="You already subscribed! /unsubscribe to stop")
				present = True
				break
	if not exist:
		subs = {}
		subs['subscribers'] = []
		with open(args["subs"], 'w') as wr:
			x = json.dumps(subs, indent=4)
			wr.write(x + '\n')
	if not present:
		name = update.effective_user.first_name
		subs['subscribers'].append({"user_name": name, "user_id": user_id})
		print("Subscribing with data: name={}, user_data={}".format(name, user_id))
		print("New subscribers list: {}".format(subs))
		with open(args["subs"], 'w') as wr:
			x = json.dumps(subs, indent=4)
			wr.write(x + '\n')
		context.bot.send_message(chat_id= update.effective_chat.id,
			text="You have been subscribed to new alerts!".format(update.effective_user.id))

def unsubscribe(update, context):
	user_id = update.effective_user.id
	exist=False
	status=False
	entry_key=-1
	sel = 0
	with open(args["subs"], 'r') as f:
		subs = json.load(f)
	if 'subscribers' in subs:
		exist=True
		for entry in subs['subscribers']:
			if entry['user_id'] == 'id':
				pass
			elif entry['user_id'] == user_id:
				status=True
				entry_key = sel
				name = entry['user_name']
				id = entry['user_id']
				print("user_id found with name: {} at entry {}.".format(name,sel))
			sel=sel+1
	if not status:
		context.bot.send_message(chat_id= update.effective_chat.id,
			text="You did not subscribed to any alerts. /subscribe")
	if not exist:
		subs = {}
		subs['subscribers']= []
		subs['subscribers'].append({"user_name": "user_id"})
		with open(args["subs"], 'w') as wr:
			x = json.dumps(subs, indent=4)
			wr.write(x + '\n')
	if status:
		subs['subscribers'].pop(entry_key)
		print("Removed subscriber {} with id {}".format(name, id))
		print("Updated subscriber list: {}".format(subs))
		with open(args["subs"], 'w') as wr:
			x = json.dumps(subs, indent=4)
			wr.write(x + '\n')
		context.bot.send_message(chat_id= update.effective_chat.id,
			text="You have been unsubscribed. /subscribe")

def update_to_user(chatid, img):
	client.bot.send_message(chat_id= chatid,
		text="Alert! Movement detected!! Sending image feed(s)... [/alarm]")
	client.bot.send_photo(chat_id= chatid, photo=open(img,'rb')) 

def main():
	# load telegram client
	dispatcher = client.dispatcher
	unknown_handler = MessageHandler(Filters.command, unknown)
	start_handler = CommandHandler('start', start)
	subscribe_handler = CommandHandler('subscribe', subscribe)
	unsubscribe_handler = CommandHandler('unsubscribe', unsubscribe)
	stop_handler = CommandHandler('stop', stop)
	help_handler = CommandHandler('help', help)
	alarm_handler = CommandHandler('alarm', alarm)

	dispatcher.add_handler(start_handler)
	dispatcher.add_handler(stop_handler)
	dispatcher.add_handler(help_handler)
	dispatcher.add_handler(subscribe_handler)
	dispatcher.add_handler(unsubscribe_handler)
	dispatcher.add_handler(alarm_handler)
	dispatcher.add_handler(unknown_handler)

	client.start_polling()
	

th = threading.Thread(target=main, args=(), daemon=True)
th.start()

# openCV for pi_surveillance

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
			with open(args['subs'],'r') as f:
				subs = json.load(f)
			if "subscribers" in subs:
				t = TempImage()
				cv2.imwrite(t.path, frame)
				for key in subs['subscribers']:
					if key['user_name'] == 'name':
						pass
					else:
						update_to_user(key['user_id'],t.path)
						print("[UPDATING] Uploading to {}".format(key['user_name']))
				t.cleanup()
				
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
			break

	# clear the stream in prepration for the next frame
	rawCapture.truncate(0)


