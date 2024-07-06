import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
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
def store_data_to_mongodb(name, age, gender, dob, blood_group, father_name, mother_name, records, image_path):
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
            data = {'name': name, 'age': age, 'gender': gender, 'dob': dob, 'blood_group': blood_group, 'father_name': father_name, 'mother_name': mother_name, 'records': records, 'image_id': file_id, 'face_encoding': encoding_list}
            collection.insert_one(data)
            print("Data stored in MongoDB")
            return True
        else:
            print("No faces found in the image")
            return False
    except Exception as e:
        print(f"Failed to store data: {e}")
        return False
    

#To get the details from each field of add_criminal_window
def select_and_store_data():
    name = add_criminal_name.get()
    age = age_entry.get()
    gender = gender_entry.get()
    dob = dob_entry.get()
    blood_group = blood_group_entry.get()
    father_name = father_name_entry.get()
    mother_name = mother_name_entry.get()
    records = records_text.get("1.0", tk.END).strip()
    image_path = filedialog.askopenfilename()
    if name and age and gender and dob and blood_group and father_name and mother_name and image_path and records:
        if store_data_to_mongodb(name, age, gender, dob, blood_group, father_name, mother_name, records, image_path):
            messagebox.showinfo("Success", "Data stored successfully!")
        else:
            messagebox.showerror("Error", "Failed to store data.")
    else:
        messagebox.showerror("Error", "Please fill in all the fields.")
    add_criminal_window.destroy()



#to delete a criminal using his name from the database
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
def send_sms(location, name):
   

    lat, lon, city, country = location
    google_maps_link = f"https://www.google.com/maps?q={lat},{lon}"
    message_body = f"Criminal Detected: {name}\nCurrent Location: {city}, {country} (Latitude: {lat}, Longitude: {lon}).\nGoogle Maps Link: {google_maps_link}"

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
                from_='+14158684503', 
                to='+918088320670'
            )
            print(f"Message sent to +918088320670: {message.sid}")
        else:
            print("No phone number found in the database.")
    except Exception as e:
        print(f"Error: {e}")

#function to reset the detected criminals history
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
            cv2.putText(frame, name, (x1, y1 - 10), cv2.FONT_HERSHEY_DUPLEX, 1, (0, 0, 200), 2)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 200), 4)

            if name not in detected_criminals:
                detected_criminals.add(name)
                # Display criminal details window immediately
                criminal_details = f"Name: {name}"
                location = get_location()
                if location:
                    send_sms(location, criminal_details)
                root.after(0, display_criminal_details_new_window, name)


        cv2.imshow("Frame", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()



#to display the detected criminals Info for 15 seconds
def display_criminal_details_new_window(name):
    criminal = collection.find_one({'name': name})
    if not criminal:
        return

    details_window = tk.Toplevel(root)
    details_window.title("Criminal Details")
    details_window.config(bg='#2c3e50')

    details_frame = tk.Frame(details_window, bg='#34495e', padx=20, pady=20)
    details_frame.pack(expand=True, fill='both', padx=20, pady=20)

    title_label = tk.Label(details_frame, text=f"Details of {name}", font=("Helvetica", 20, "bold"), bg='#34495e', fg='white')
    title_label.grid(row=0, column=0, columnspan=2, pady=10)

    

    labels = ["Name", "Age", "Gender", "DOB", "Blood Group", "Father's Name", "Mother's Name", "Records"]
    values = [criminal.get('name', ''), criminal.get('age', ''), criminal.get('gender', ''), 
              criminal.get('dob', ''), criminal.get('blood_group', ''), criminal.get('father_name', ''), 
              criminal.get('mother_name', ''), criminal.get('records', '')]
    
    for i, (label, value) in enumerate(zip(labels, values)):
        tk.Label(details_frame, text=f"{label}:", font=("Helvetica", 15), bg='#34495e', fg='white').grid(row=i+1, column=0, padx=10, pady=10, sticky="e")
        tk.Label(details_frame, text=value, font=("Helvetica", 15), bg='#34495e', fg='white').grid(row=i+1, column=1, padx=10, pady=10, sticky="w")

    # Load and display the image associated with the criminal
    image_id = criminal.get('image_id', '')
    if image_id:
        try:
            image_data = fs.get(image_id).read()
            image = Image.open(io.BytesIO(image_data))
            image = image.convert("RGB")
            image = image.resize((200, 200), Image.ANTIALIAS)

            img = ImageTk.PhotoImage(image)
            img_label = tk.Label(details_frame, image=img)
            img_label.image = img  
            img_label.grid(row=len(labels)+1, column=0, columnspan=2, pady=10)
        except Exception as e:
            print(f"Error loading image for {name}: {e}")    

    # Automatically close the details window after 15 seconds
    details_window.after(15000, details_window.destroy)


#GUI to add a criminal to the database
def open_add_criminal_window():
    global add_criminal_name, add_criminal_image_label, age_entry, records_text, gender_entry, dob_entry, blood_group_entry, father_name_entry, mother_name_entry, add_criminal_window
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

    gender_label = tk.Label(add_criminal_frame, text="Gender:", font=("Helvetica", 15), bg='#34495e', fg='white')
    gender_label.grid(row=3, column=0, padx=10, pady=10, sticky="e")
    gender_entry = tk.Entry(add_criminal_frame, font=("Helvetica", 15), width=30)
    gender_entry.grid(row=3, column=1, padx=10, pady=10)

    dob_label = tk.Label(add_criminal_frame, text="DOB:", font=("Helvetica", 15), bg='#34495e', fg='white')
    dob_label.grid(row=4, column=0, padx=10, pady=10, sticky="e")
    dob_entry = tk.Entry(add_criminal_frame, font=("Helvetica", 15), width=30)
    dob_entry.grid(row=4, column=1, padx=10, pady=10)

    blood_group_label = tk.Label(add_criminal_frame, text="Blood Group:", font=("Helvetica", 15), bg='#34495e', fg='white')
    blood_group_label.grid(row=5, column=0, padx=10, pady=10, sticky="e")
    blood_group_entry = tk.Entry(add_criminal_frame, font=("Helvetica", 15), width=30)
    blood_group_entry.grid(row=5, column=1, padx=10, pady=10)

    father_name_label = tk.Label(add_criminal_frame, text="Father's Name:", font=("Helvetica", 15), bg='#34495e', fg='white')
    father_name_label.grid(row=6, column=0, padx=10, pady=10, sticky="e")
    father_name_entry = tk.Entry(add_criminal_frame, font=("Helvetica", 15), width=30)
    father_name_entry.grid(row=6, column=1, padx=10, pady=10)

    mother_name_label = tk.Label(add_criminal_frame, text="Mother's Name:", font=("Helvetica", 15), bg='#34495e', fg='white')
    mother_name_label.grid(row=7, column=0, padx=10, pady=10, sticky="e")
    mother_name_entry = tk.Entry(add_criminal_frame, font=("Helvetica", 15), width=30)
    mother_name_entry.grid(row=7, column=1, padx=10, pady=10)

    records_label = tk.Label(add_criminal_frame, text="Records:", font=("Helvetica", 15), bg='#34495e', fg='white')
    records_label.grid(row=8, column=0, padx=10, pady=10, sticky="ne")
    records_text = tk.Text(add_criminal_frame, height=4, width=30, font=("Helvetica", 15))
    records_text.grid(row=8, column=1, padx=10, pady=10)

    save_btn = tk.Button(add_criminal_frame, text="Select Image And Upload Details", command=select_and_store_data, **btn_style1)
    save_btn.grid(row=9, column=0, columnspan=2, padx=10, pady=20, sticky="we")



#GUI to delete a criminal from the database
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

    remove_btn = tk.Button(remove_criminal_frame, text="Remove", command=delete_image, **btn_style1)
    remove_btn.grid(row=3, column=0, columnspan=2, padx=10, pady=20)

#button style for windows buttons
btn_style1 = {
    'font': ("Helvetica", 20),
    'bg': '#F7E7DC',
    'fg': 'black',
    'activebackground': '#E6B9A6',
    'activeforeground': 'white',
    'bd': 0,
    'relief': 'flat',
    'width': 20,
    'height': 2
}
#The Main GUI of the project

root = tk.Tk()
root.title("Criminal Identification")
root.geometry("1500x1000")

# Load the background image
bg_image = Image.open("background.jpg")  # Replace with your image path
bg_image = bg_image.resize((1800, 1000), Image.ANTIALIAS)
bg_photo = ImageTk.PhotoImage(bg_image)

# Create a Canvas and add the background image
canvas = tk.Canvas(root, width=1500, height=1000)
canvas.pack(fill='both', expand=True)
canvas.create_image(0, 0, image=bg_photo, anchor='nw')
canvas.create_text(750, 100, text="Criminal Identification", font=("Helvetica", 80, "bold"), fill="#F7E7DC")# Create a title label directly on the canvas
# title_label = tk.Label(root, text="Criminal Identification", font=("Helvetica", 40, "bold"), fg='white', bg='#2c3e50')
# canvas.create_window(750, 100, window=title_label)  # Position title at the top center

btn_style = {
    'font': ("Helvetica", 20),
    'bg': '#F7E7DC',
    'fg': 'black',
    'activebackground': '#E6B9A6',
    'activeforeground': 'white',
    'bd': 0,
    'relief': 'flat',
    'width': 20,
    'height': 3
}

# Create buttons
add_btn = tk.Button(root, text="Add Criminal", command=open_add_criminal_window, **btn_style)
remove_btn = tk.Button(root, text="Remove Criminal", command=open_remove_criminal_window, **btn_style)
detect_btn = tk.Button(root, text="Detect Criminal", command=detect_criminal, **btn_style)
exit_btn = tk.Button(root, text="Exit", command=root.quit, **btn_style)

# Align buttons in a column
buttons = [add_btn, remove_btn, detect_btn, exit_btn]
start_y = 250
spacing = 150  # Increase spacing to add bottom margin
for i, btn in enumerate(buttons):
    canvas.create_window(750, start_y + i * spacing, window=btn)




sfr.load_encoding_images()
root.mainloop()