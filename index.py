import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image
import cv2
import gridfs
import face_recognition
import pymongo
import io
import numpy as np
import requests
from twilio.rest import Client
import math
import threading
import time


# Connecting to Mongo Database
client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client["criminals"]
collection = db["criminals"]
phone_collection = db["phone_numbers"]
fs = gridfs.GridFS(db)


class SimpleFacerec:
    def __init__(self):
        self.known_face_encodings = []
        self.known_face_names = []
        self.frame_resizing = 0.25

    def load_encoding_images(self):
        # Calling the encoding function to encode all images in collection
        for document in collection.find():
            image_url = document['image_id'] 
            criminal_name = document['name']  
            encoding = encode_image_from_url(image_url)
            if encoding is not None:
                self.known_face_encodings.append(encoding[0])
                self.known_face_names.append(criminal_name)
        print("Encoding images loaded")
        print(self.known_face_names)

    # Function to compare the faces captured and faces stored in the database
    def detect_known_faces(self, frame):
        # Resizing the image and detecting face through Camera
        small_frame = cv2.resize(frame, (0, 0), fx=self.frame_resizing, fy=self.frame_resizing)
        rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_small_frame)
        face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

        face_names = []
        # Comparing the faces
        for face_encoding in face_encodings:
            matches = face_recognition.compare_faces(self.known_face_encodings, face_encoding)
            face_distances = face_recognition.face_distance(self.known_face_encodings, face_encoding)
            best_match_index = np.argmin(face_distances)
            if matches[best_match_index]:
                name = self.known_face_names[best_match_index]
                face_names.append(name)

        face_locations = np.array(face_locations)
        face_locations = face_locations / self.frame_resizing
        return face_locations.astype(int), face_names

sfr = SimpleFacerec()

# Function to retrieve the images from MongoDB and encode them
def encode_image_from_url(file_id):
    try:
        file = fs.get(file_id)
        if not file:
            print(f"No file found with the id {file_id}")
            return

        image_data = file.read()
        image = Image.open(io.BytesIO(image_data))  

        image = image.convert("RGB")
        # Convert the image to a numpy array
        image_np = np.array(image)   

        # Find face locations and encodings
        face_locations = face_recognition.face_locations(image_np)
        face_encodings = face_recognition.face_encodings(image_np, face_locations)
        
        if len(face_encodings) > 0:
            return face_encodings
        else:
            print("No faces found in the image:", file_id)
            return None
    except Exception as e:
        print("Error processing image from", file_id, ":", e)
        return None

# Global variables
add_criminal_image_label = None
add_criminal_name = None
add_criminal_window=None
remove_criminal_window_name=None


#to upload details to mongoDB
def store_data_to_mongodb(name, age, records, image_path):
    try:
        # Read the image file
        with open(image_path, 'rb') as f:
            image_data = f.read()

        # Store the image in GridFS
        file_id = fs.put(image_data, filename=image_path.split('/')[-1])
        print(f"Image {image_path} stored in MongoDB with id: {file_id}")

        # Load the image using face_recognition
        image = face_recognition.load_image_file(image_path)
        # Get the face encodings
        face_encodings = face_recognition.face_encodings(image)

        if face_encodings:
            encoding = face_encodings[0]  # Take the first encoding found
            # Convert the encoding to a list for storage in MongoDB
            encoding_list = encoding.tolist()
            # Store the data along with the image encoding in the criminals collection
            data = {'name': name, 'age': age,'records':records, 'image_id': file_id}
            collection.insert_one(data)
            print("Data stored in MongoDB")
            return True
        else:
            print("No faces found in the image")
            return False
    except Exception as e:
        print(f"Failed to store data: {e}")
        return False

def select_and_store_data():
    name = add_criminal_name.get()
    age = age_entry.get()
    records = records_text.get("1.0", tk.END).strip()
    image_path = filedialog.askopenfilename()
    if name and age and image_path and records:
        if store_data_to_mongodb(name, age,records, image_path):
            messagebox.showinfo("Success", "Data stored successfully!")
        else:
            messagebox.showerror("Error", "Failed to store data.")
    else:
        messagebox.showerror("Error", "Please fill in all the fields.")
    add_criminal_window.destroy()


def delete_image():
    name=remove_criminal_window_name.get()
    if not name:
        messagebox.showwarning("Input Error", "Please provide all details and an image.")
        return
    collection.delete_one({"name":name})
    messagebox.showinfo("Success", "Criminal details Deleted successfully.")
    open_remove_criminal.destroy()


# Function to get current location
def get_location():
    try:
        response = requests.get("http://ip-api.com/json/")
        data = response.json()
        if data['status'] == 'success':
            return data['lat'], data['lon'], data['city'], data['country']
        else:
            return None
    except Exception as e:
        print(f"Error: {e}")
        return None

# Function to send SMS with criminal location and details
def send_sms(location, details):
    account_sid = 'ACe6f312ed161307877c3e6514d5bb3f55'
    auth_token = '7c115cf3c483b3b8043987a1fd99a2e4'
    client = Client(account_sid, auth_token)

    lat, lon, city, country = location
    google_maps_link = f"https://www.google.com/maps?q={lat},{lon}"
    message_body = f"Criminal Detected: {details}\nCurrent Location: {city}, {country} (Latitude: {lat}, Longitude: {lon}).\nGoogle Maps Link: {google_maps_link}"

    try:
        # Retrieve phone numbers from the database
        phone_numbers = phone_collection.find({}, {"_id": 0, "phone": 1, "lat": 1, "lon": 1})

        # Calculate the nearest phone number
        nearest_phone_number = None
        min_distance = math.inf
        for phone_number in phone_numbers:
            phone_lat = phone_number["lat"]
            phone_lon = phone_number["lon"]
            distance = math.sqrt((lat - phone_lat) ** 2 + (lon - phone_lon) ** 2)
            if distance < min_distance:
                min_distance = distance
                nearest_phone_number = phone_number["phone"]

        if nearest_phone_number:
            # Send SMS to the nearest phone number
            message = client.messages.create(
                body=message_body,
                from_='+13148876858', 
                to=nearest_phone_number
            )
            print(f"Message sent to {nearest_phone_number}: {message.sid}")
        else:
            print("No phone number found in the database.")
    except Exception as e:
        print(f"Error: {e}")

# Function to detect criminal using camera
def reset_detected_criminals():
    global detected_criminals
    while True:
        time.sleep(900)  # Sleep for 900 seconds (15 minutes)
        detected_criminals.clear()

def detect_criminal():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        messagebox.showerror("Camera Error", "Cannot open camera. Please check if the camera is connected and accessible.")
        return

    global detected_criminals
    detected_criminals = set()

    # Start the timer thread to reset the set every 15 minutes
    reset_thread = threading.Thread(target=reset_detected_criminals, daemon=True)
    reset_thread.start()

    while True:
        ret, frame = cap.read()
        if not ret:
            messagebox.showerror("Frame Error", "Failed to capture frame from camera.")
            break

        face_locations, face_names = sfr.detect_known_faces(frame)
        for face_loc, name in zip(face_locations, face_names):
            y1, x2, y2, x1 = face_loc[0], face_loc[1], face_loc[2], face_loc[3]
            # Writing Text above the frame
            cv2.putText(frame, name, (x1, y1 - 10), cv2.FONT_HERSHEY_DUPLEX, 1, (0, 0, 200), 2)
            # Drawing the frame
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 200), 4)
            
            if name not in detected_criminals:
                detected_criminals.add(name)
                criminal_details = f"Name: {name}"
                location = get_location()
                if location:
                    send_sms(location, criminal_details)

        cv2.imshow("Frame", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

import tkinter as tk
from tkinter import messagebox


# Function to open the add criminal window
def open_add_criminal_window():
    global add_criminal_name, add_criminal_image_label, age_entry, records_text, add_criminal_window
    add_criminal_window = tk.Toplevel(root)
    add_criminal_window.title("Add Criminal")
    add_criminal_window.config(bg='#2c3e50')

    add_criminal_frame = tk.Frame(add_criminal_window, bg='#34495e', padx=20, pady=20)
    add_criminal_frame.pack(expand=True, fill='both', padx=20, pady=20)

    title_label = tk.Label(add_criminal_frame, text="Add Criminal", font=("Helvetica", 20, "bold"), bg='#34495e', fg='white')
    title_label.grid(row=0, column=0, columnspan=2, pady=10)

    name_label = tk.Label(add_criminal_frame, text="Name:", font=("Helvetica", 15), bg='#34495e', fg='white')
    name_label.grid(row=1, column=0, padx=10, pady=10, sticky="e")
    add_criminal_name = tk.Entry(add_criminal_frame, font=("Helvetica", 15), width=30)
    add_criminal_name.grid(row=1, column=1, padx=10, pady=10)

    age_label = tk.Label(add_criminal_frame, text="Age:", font=("Helvetica", 15), bg='#34495e', fg='white')
    age_label.grid(row=2, column=0, padx=10, pady=10, sticky="e")
    age_entry = tk.Entry(add_criminal_frame, font=("Helvetica", 15), width=30)
    age_entry.grid(row=2, column=1, padx=10, pady=10)

    records_label = tk.Label(add_criminal_frame, text="Records:", font=("Helvetica", 15), bg='#34495e', fg='white')
    records_label.grid(row=3, column=0, padx=10, pady=10, sticky="ne")
    records_text = tk.Text(add_criminal_frame, height=4, width=30, font=("Helvetica", 15))
    records_text.grid(row=3, column=1, padx=10, pady=10)

    save_btn = tk.Button(add_criminal_frame, text="Select Image And Upload Details", command=select_and_store_data, **btn_style)
    save_btn.grid(row=5, column=0, columnspan=2, padx=10, pady=20, sticky="we")

    
def open_remove_criminal_window():
    global open_remove_criminal, remove_criminal_window_name
    open_remove_criminal = tk.Toplevel(root)
    open_remove_criminal.title("Remove Criminal")
    open_remove_criminal.config(bg='#2c3e50')

    remove_criminal_frame = tk.Frame(open_remove_criminal, bg='#34495e', padx=20, pady=20)
    remove_criminal_frame.pack(expand=True, fill='both', padx=20, pady=20)

    title_label = tk.Label(remove_criminal_frame, text="Remove Criminal", font=("Helvetica", 20, "bold"), bg='#34495e', fg='white')
    title_label.grid(row=0, column=0, columnspan=2, pady=10)

    name_label = tk.Label(remove_criminal_frame, text="Name:", font=("Helvetica", 15), bg='#34495e', fg='white')
    name_label.grid(row=1, column=0, padx=10, pady=10, sticky="e")
    remove_criminal_window_name = tk.Entry(remove_criminal_frame, font=("Helvetica", 15), width=30)
    remove_criminal_window_name.grid(row=1, column=1, padx=10, pady=10)

    age_label = tk.Label(remove_criminal_frame, text="Age:", font=("Helvetica", 15), bg='#34495e', fg='white')
    age_label.grid(row=2, column=0, padx=10, pady=10, sticky="e")
    age_entry1 = tk.Entry(remove_criminal_frame, font=("Helvetica", 15), width=30)
    age_entry1.grid(row=2, column=1, padx=10, pady=10)

    remove_btn = tk.Button(remove_criminal_frame, text="Remove", command=delete_image, **btn_style)
    remove_btn.grid(row=3, column=0, columnspan=2, padx=10, pady=20)

# Create the main window
root = tk.Tk()
root.title("Criminal Identification")

# Make the window fullscreen
root.attributes('-fullscreen', True)

# Set the background color
root.config(bg='#2c3e50')

# Create and configure the main frame
frame = tk.Frame(root, bg='#34495e', padx=20, pady=20)
frame.pack(expand=True, fill='both')

# Create and place the title label
title_label = tk.Label(frame, text="Criminal Identification", font=("Helvetica", 30, "bold"), bg='#34495e', fg='white')
title_label.pack(pady=20)

# Create and place the buttons
btn_frame = tk.Frame(frame, bg='#34495e')
btn_frame.pack(pady=20)

btn_style = {
    'font': ("Helvetica", 15),
    'bg': '#2980b9',
    'fg': 'white',
    'activebackground': '#3498db',
    'activeforeground': 'white',
    'bd': 0,
    'relief': 'flat',
    'width': 20,
    'height': 2
}

add_btn = tk.Button(btn_frame, text="Add Criminal", command=open_add_criminal_window, **btn_style)
add_btn.grid(row=0, column=0, padx=20, pady=20)

delete_btn = tk.Button(btn_frame, text="Remove Criminal", command=open_remove_criminal_window, **btn_style)
delete_btn.grid(row=1, column=0, padx=20, pady=20)

detect_btn = tk.Button(btn_frame, text="Detect Criminal", command=detect_criminal, **btn_style)
detect_btn.grid(row=2, column=0, padx=20, pady=20)

exit_btn = tk.Button(btn_frame, text="Exit", command=root.quit, **btn_style)
exit_btn.grid(row=3, column=0, padx=20, pady=20)

# Load encoding images
sfr.load_encoding_images()
root.mainloop()