from flask import Flask, render_template, redirect, flash, url_for, request
import sqlite3
from helpers import *
from werkzeug.utils import secure_filename
from google.cloud import storage
from flask_bootstrap import Bootstrap
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from flask_socketio import SocketIO, join_room, leave_room, emit
from flask_login import LoginManager, current_user, login_user, logout_user, UserMixin, login_required, login_manager
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, current_user, login_user, logout_user, UserMixin, login_required

app = Flask(__name__)
socketio = SocketIO(app)
storage_client = storage.Client.from_service_account_json(
    r'C:\Users\amogus\Downloads\instagram-388019-403991a5adf6.json')
bucket_name = 'instaclonebucket2'

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///instagram.db'
app.config['SECRET_KEY'] = 'hss3uro2hsxfogfq'
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=7)
app.config['REMEMBER_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_SECURE'] = True
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)

login_manager.login_view = 'login'


class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    number = db.Column(db.String(120), unique=True, nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    posts = db.relationship('Post', back_populates='user', lazy='dynamic')  # change 'author' to 'user'


class Post(db.Model):
    __tablename__ = 'posts'
    id = db.Column(db.Integer, primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    caption = db.Column(db.String(1000))
    images = db.relationship('Image', backref='post', lazy=True)
    user = db.relationship('User', back_populates="posts")  # change 'author' to 'user'


class Image(db.Model):
    __tablename__ = 'images'
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False)
    image_url = db.Column(db.String(500), nullable=False)

class Room(db.Model):
    __tablename__ = 'rooms'
    id = db.Column(db.Integer, primary_key=True)
    room_number = db.Column(db.String(50), unique=True, nullable=False)
    messages = db.relationship('Message', back_populates='room', lazy='dynamic')

class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.String(500), nullable=False)
    sender = db.relationship('User', backref="messages")
    room = db.relationship('Room', back_populates="messages")


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/')
@login_required
def home():
    posts = Post.query.order_by(Post.id.desc()).all()

    return render_template("index.html", active_menu='home', posts=posts)


@app.route('/signup', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = RegistrationForm()
    if form.validate_on_submit():
        number = form.number.data
        password = form.password.data
        name = form.name.data
        username = form.username.data
        if User.query.filter_by(number=number).first():
            flash('Number already registered.')
            return redirect(url_for('register'))
        new_user = User(
            name=name,
            username=username,
            number=number,
            password=generate_password_hash(password))
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful.')
        login_user(new_user, remember=True)
        return redirect(url_for('home'))
    elif request.method == 'POST':
        if not form.number.data:
            flash('Please enter a phone number.', 'error')
        elif not form.password.data:
            flash('Please enter a password.', 'error')
        elif not form.name.data:
            flash('Please enter a name.', 'error')
        elif not form.username.data:
            flash('Please enter a username.', 'error')
        else:
            flash('Account not created. Please check your input and try again.', 'error')
    return render_template('signup.html', form=form)


@app.route('/login', methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = LoginForm()
    if form.validate_on_submit():
        number = form.number.data
        password = form.password.data
        user = User.query.filter_by(number=number).first()
        if user:
            if check_password_hash(user.password, password):
                login_user(user, remember=True)
                return redirect(url_for('home'))
            else:
                flash('Incorrect password.', 'error')
                return redirect(url_for('login'))  # Add this line

        else:
            flash('Phone number not registered.', 'error')
            return redirect(url_for('login'))  # Add this line

    elif request.method == 'POST':
        if not form.number.data:
            flash('Please enter a phone number.', 'error')
        elif not form.password.data:
            flash('Please enter a password.', 'error')
        else:
            flash('Check credentials', 'error')
    return render_template('login.html', form=form)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))


@app.route("/create", methods=["POST", "GET"])
@login_required
def create():
    if request.method == "POST":
        caption = request.form.get("caption")
        image_url = request.form.get("image_url")
        new_post = Post(
            author_id=current_user.id,
            caption=caption
        )
        db.session.add(new_post)
        db.session.commit()

        new_image = Image(
            post_id=new_post.id,
            image_url=image_url
        )
        db.session.add(new_image)
        db.session.commit()

        flash('Post created successfully.')
        return redirect(url_for('home'))
    return render_template('create.html', active_menu='create')


@app.route('/upload', methods=['POST', "GET"])
def upload():
    if request.method == 'POST':
        if 'file' not in request.files:
            return {"error": "No file part"}, 400

        file = request.files['file']
        if file.filename == '':
            return {"error": "No selected file"}, 400

        filename = secure_filename(file.filename)
        blob = storage_client.get_bucket(bucket_name).blob(filename)
        blob.upload_from_string(
            file.read(),
            content_type=file.content_type
        )

        url = blob.public_url
        return {"url": url}

    return {"error": "Method not allowed"}, 405


@app.route("/search")
@login_required
def search():
    return render_template('search.html', active_menu='search')


@app.route("/explore")
@login_required
def explore():
    return render_template('explore.html', active_menu='explore')

@app.route("/messages")
@login_required
def messages():
    user_id = current_user.id
    all_rooms = Room.query.all()
    user_rooms = []

    for room in all_rooms:
        room_id = [int(id) for id in room.room_number.split('-')]
        if user_id in room_id:
            # Extract the id of the other user
            other_user_ids = [id for id in room_id if id != user_id]
            if other_user_ids:  # Only add rooms where another user is present
                other_user_id = other_user_ids[0]  # Get the first id
                other_username = User.query.get(other_user_id).username
                last_message = Message.query.filter_by(room_id=room.id).order_by(Message.id.desc()).first()
                if last_message:
                    last_message_text = last_message.content
                else:
                    last_message_text = "No messages yet"
                user_rooms.append((room, other_username, last_message_text, other_user_id))  # Store room with other user's username and the last message

    return render_template('messages.html', rooms=user_rooms, active_menu='messages', username=current_user.username)




@app.route("/save_username", methods=["POST"])
def save_username():
    username = request.form.get("username")
    if username:
        user = User.query.filter_by(username=username).first()
        if user and user != current_user:
            return {"redirect": url_for('messageUser', user_id=user.id)}
        else:
            return {"error": "Username not found"}, 400
    else:
        return {"error": "No username provided"}, 400


@app.route('/message/<user_id>')
@login_required
def messageUser(user_id):
    user = User.query.get(user_id)

    if user:
        room_number = f"{min(current_user.id, user.id)}-{max(current_user.id, user.id)}"
        room = Room.query.filter_by(room_number=room_number).first()
        if room is None:
            room = Room(room_number=room_number)
            db.session.add(room)
            db.session.commit()
        messages = Message.query.filter_by(room_id=room.id).all()
        return render_template('messageUser.html', username=user.username, room=room_number, messages=messages)
    else:
        flash('User not found.', 'error')
        return redirect(url_for('home'))

@socketio.on('join')
def on_join(data):
    username = data['username']
    room = data['room']
    join_room(room)
    room_instance = Room.query.filter_by(room_number=room).first()
    if not room_instance:
        room_instance = Room(room_number=room)
        db.session.add(room_instance)
        db.session.commit()

@socketio.on('message')
def on_message(data):
    emit('message', data, room=data['room'])
    room = Room.query.filter_by(room_number=data['room']).first()
    if room:
        user = User.query.filter_by(username=data['username']).first()
        if user:
            msg = Message(content=data['message'], room_id=room.id, sender_id=user.id)
            db.session.add(msg)
            db.session.commit()

@app.route("/notifications")
@login_required
def notifications():
    return render_template('notifications.html', active_menu='notifications')


@app.route("/posts/<int:id>")
@login_required
def posts(id):
    post = Post.query.get_or_404(id)
    user = User.query.get(post.author_id)
    return render_template('post.html', post=post, user=user, active_menu='home')


@app.route("/profile")
@login_required
def profileSelf():
    return redirect(url_for('profile', user_id=current_user.id))


@app.route("/profile/<int:user_id>")
@login_required
def profile(user_id):
    user = User.query.get(user_id)
    if user:
        all_posts = user.posts.order_by(Post.id.desc()).all()
        posts = [all_posts[i] for i in range(0, len(all_posts), 3)]
        posts2 = [all_posts[i] for i in range(1, len(all_posts), 3)]
        posts3 = [all_posts[i] for i in range(2, len(all_posts), 3)]
        return render_template('profile.html', active_menu='profile', user=user, posts=posts, posts2=posts2,
                               posts3=posts3)
    else:
        flash('User not found.', 'error')
        return redirect(url_for('home'))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
