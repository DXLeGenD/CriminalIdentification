import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import cv2
import face_recognition
import pymongo
import requests
import numpy as np

# Connecting to Mongo Database
client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client["criminals"]
collection = db["criminals"]

# Function to retrieve the images from MongoDB and encode them
def encode_image_from_url(url):
    try:
        # If the image is stored in Google Drive
        if "drive.google.com" in url:
            file_id = url.split("/")[5]
            url = f"https://drive.google.com/uc?id={file_id}"
        
        # Fetch the image if the image is taken from online
        response = requests.get(url)
        if response.status_code != 200:
            print(f"Failed to fetch image from {url}. Status code: {response.status_code}")
            return None
        
        image = cv2.imdecode(np.frombuffer(response.content, np.uint8), -1)

        # Find face locations and encodings
        face_locations = face_recognition.face_locations(image)
        face_encodings = face_recognition.face_encodings(image, face_locations)
        
        if len(face_encodings) > 0:
            return face_encodings
        else:
            print("No faces found in the image:", url)
            return None
    except Exception as e:
        print("Error processing image from", url, ":", e)
        return None

class SimpleFacerec:
    def __init__(self):
        self.known_face_encodings = []
        self.known_face_names = []
        self.frame_resizing = 0.25

    def load_encoding_images(self):
        # Calling the encoding function to encode all images in collection
        for document in collection.find():
            image_url = document['image'] 
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

# Global variables
add_criminal_image_label = None
add_criminal_name = None
add_criminal_window = None
age_entry = None
records_text = None
remove_criminal_window_name = None
loaded_image_encoding = None

def upload():
    name = add_criminal_name.get()
    age = age_entry.get()
    records = records_text.get("1.0", tk.END).strip()
    
    if not name or not age or loaded_image_encoding is None:
        messagebox.showwarning("Input Error", "Please provide all details and an image.")
        return

    # Upload details to MongoDB
    collection.insert_one({
        "name": name,
        "age": age,
        "records": records,
        "image": "Image Place Holder"
    })

    messagebox.showinfo("Success", "Criminal details uploaded successfully.")
    add_criminal_window.destroy()

# Function to open file dialog and load an image
def load_image():
    global loaded_image, loaded_image_encoding, add_criminal_image_label
    file_path = filedialog.askopenfilename(filetypes=[("Image files", "*.jpg;*.jpeg;*.png;*.bmp")])
    if file_path:
        img = Image.open(file_path)
        img.thumbnail((200, 200)) # Resize image to fit in label
        img = ImageTk.PhotoImage(img)
        add_criminal_image_label.config(image=img)
        add_criminal_image_label.image = img # Keep a reference to avoid garbage collection
        
        # Load the image for face recognition
        loaded_image = cv2.imread(file_path)
        loaded_image_encoding = face_recognition.face_encodings(loaded_image)[0]

def delete_image():
    name = remove_criminal_window_name.get()
    if not name:
        messagebox.showwarning("Input Error", "Please provide all details and an image.")
        return
    collection.delete_one({"name": name})
    messagebox.showinfo("Success", "Criminal details deleted successfully.")
    open_remove_criminal.destroy()

# Function to detect criminal using camera
def detect_criminal():
    cap = cv2.VideoCapture(0)
    while True:
        ret, frame = cap.read()
        face_locations, face_names = sfr.detect_known_faces(frame)
        for face_loc, name in zip(face_locations, face_names):
            y1, x2, y2, x1 = face_loc[0], face_loc[1], face_loc[2], face_loc[3]
            # Writing Text above the frame
            cv2.putText(frame, name, (x1, y1 - 10), cv2.FONT_HERSHEY_DUPLEX, 1, (0, 0, 200), 2)
            # Drawing the frame
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 200), 4)
        cv2.imshow("Frame", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    cap.release()
    cv2.destroyAllWindows()

# Function to open the add criminal window
def open_add_criminal_window():
    global add_criminal_name, add_criminal_image_label, age_entry, records_text, add_criminal_window
    add_criminal_window = tk.Toplevel(root)
    add_criminal_window.title("Add Criminal")
    add_criminal_window.config(bg='#2c3e50')
    
    add_criminal_frame = tk.Frame(add_criminal_window, bg='#34495e', padx=20, pady=20)
    add_criminal_frame.pack(padx=10, pady=10)
    
    add_criminal_image_label = tk.Label(add_criminal_frame, bg='#34495e')
    add_criminal_image_label.grid(row=0, column=0, padx=10, pady=10, columnspan=2)

    image_btn = tk.Button(add_criminal_frame, text="Select Image", command=load_image, **btn_style)
    image_btn.grid(row=4, column=0, padx=10, pady=10, columnspan=2)

    name_label = tk.Label(add_criminal_frame, text="Name:", font=("Helvetica", 12), bg='#34495e', fg='white')
    name_label.grid(row=1, column=0, padx=10, pady=10, sticky="e")
    add_criminal_name = tk.Entry(add_criminal_frame, font=("Helvetica", 12), width=20)
    add_criminal_name.grid(row=1, column=1, padx=10, pady=10)

    age_label = tk.Label(add_criminal_frame, text="Age:", font=("Helvetica", 12), bg='#34495e', fg='white')
    age_label.grid(row=2, column=0, padx=10, pady=10, sticky="e")
    age_entry = tk.Entry(add_criminal_frame, font=("Helvetica", 12), width=20)
    age_entry.grid(row=2, column=1, padx=10, pady=10)

    records_label = tk.Label(add_criminal_frame, text="Records:", font=("Helvetica", 12), bg='#34495e', fg='white')
    records_label.grid(row=3, column=0, padx=10, pady=10, sticky="ne")
    records_text = tk.Text(add_criminal_frame, height=4, width=20, font=("Helvetica", 12))
    records_text.grid(row=3, column=1, padx=10, pady=10)

    save_btn = tk.Button(add_criminal_frame, text="Upload Details", command=upload, **btn_style)
    save_btn.grid(row=5, column=0, columnspan=2, padx=10, pady=10)

def open_remove_criminal_window():
    global open_remove_criminal, remove_criminal_window_name
    open_remove_criminal = tk.Toplevel(root)
    open_remove_criminal.title("Remove Criminal")
    open_remove_criminal.config(bg='#34495e')

    remove_criminal_frame = tk.Frame(open_remove_criminal, bg='#34495e', padx=20, pady=20)
    remove_criminal_frame.pack(padx=10, pady=10)

    remove_criminal_label = tk.Label(remove_criminal_frame, bg='#34495e')
    remove_criminal_label.grid(row=0, column=0, padx=10, pady=10, columnspan=2)

    name_label = tk.Label(remove_criminal_frame, text="Name:", font=("Helvetica", 12), bg='#34495e', fg='white')
    name_label.grid(row=1, column=0, padx=10, pady=10, sticky="e")
    remove_criminal_window_name = tk.Entry(remove_criminal_frame, font=("Helvetica", 12), width=20)
    remove_criminal_window_name.grid(row=1, column=1, padx=10, pady=10)

    age_label = tk.Label(remove_criminal_frame, text="Age:", font=("Helvetica", 12), bg='#34495e', fg='white')
    age_label.grid(row=2, column=0, padx=10, pady=10, sticky="e")
    age_entry1 = tk.Entry(remove_criminal_frame, font=("Helvetica", 12), width=20)
    age_entry1.grid(row=2, column=1, padx=10, pady=10)

    remove_btn = tk.Button(remove_criminal_frame, text="Remove", command=delete_image, **btn_style)
    remove_btn.grid(row=5, column=0, columnspan=2, padx=10, pady=10)

# Create the main window
root = tk.Tk()
root.title("Criminal Identification")

# Set the background color
root.config(bg='#2c3e50')

# Create and configure the main frame
frame = tk.Frame(root, bg='#34495e', padx=20, pady=20)
frame.pack(padx=10, pady=10)

# Create and place the title label
title_label = tk.Label(frame, text="Criminal Identification", font=("Helvetica", 20, "bold"), bg='#34495e', fg='white')
title_label.pack(pady=10)

# Create and place the buttons
btn_frame = tk.Frame(frame, bg='#34495e')
btn_frame.pack(pady=10)

btn_style = {
    'font': ("Helvetica", 12),
    'bg': '#2980b9',
    'fg': 'white',
    'activebackground': '#3498db',
    'activeforeground': 'white',
    'bd': 0,
    'relief': 'flat',
    'width': 15,
    'height': 2
}

add_btn = tk.Button(btn_frame, text="Add Criminal", command=open_add_criminal_window, **btn_style)
add_btn.grid(row=0, column=0, padx=10, pady=10)

delete_btn = tk.Button(btn_frame, text="Remove Criminal", command=open_remove_criminal_window, **btn_style)
delete_btn.grid(row=0, column=1, padx=10, pady=10)

detect_btn = tk.Button(frame, text="Detect Criminal", command=detect_criminal, **btn_style)
detect_btn.pack(pady=10)

sfr.load_encoding_images()

# Run the application
root.mainloop()
