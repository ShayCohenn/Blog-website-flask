import os
import smtplib
from typing import Final
from datetime import date
from dotenv import load_dotenv
from sqlalchemy.engine.result import Result
from flask import Flask, abort, render_template, redirect, url_for, flash
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_login import login_user, LoginManager, current_user, logout_user
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from forms import CreatePostForm, RegisterForm, LoginForm, CommentForm, ContactForm
from models import Comment, BlogPost, User, db, UserMixin
from flask_migrate import Migrate

load_dotenv()

DB: Final[str] = os.getenv('DB')
SECRET_KEY: Final[str] = os.getenv('SECRET_KEY')

FROM_EMAIL: Final[str] = os.getenv('FROM_EMAIL')
PASSWORD: Final[str] = os.getenv('PASSWORD')
TO_EMAIL: Final[str] = os.getenv('TO_EMAIL')

def send_email(message: str) -> None:
     with smtplib.SMTP("smtp.gmail.com") as connection:
        connection.starttls()
        connection.login(FROM_EMAIL, PASSWORD)
        connection.sendmail(from_addr=FROM_EMAIL, to_addrs=TO_EMAIL, msg=message)
        connection.quit()

def construct_msg(name: str, email: str, phone_number: str, msg: str) -> str:
    message: str = f"""Subject: Blog Website Contact \nFrom: noreply <{FROM_EMAIL}> \n\n
                        You got a contact message \n
                        From: {name} \n
                        email: {email} \n
                        phone number: {phone_number} \n
                        message: {msg}"""
    return message

app: Flask = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
ckeditor = CKEditor(app)
Bootstrap5(app)

# Configure Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
current_user: UserMixin


@login_manager.user_loader
def load_user(user_id):
    return db.get_or_404(User, user_id)

def gravatar_url(size=100, rating='g', default='retro', force_default=False):
    return f"https://www.gravatar.com/avatar/?s={size}&d={default}&r={rating}&f={force_default}"

app.config['SQLALCHEMY_DATABASE_URI'] = DB
migrate = Migrate(app, db)
db.init_app(app)

# Create an admin-only decorator
def admin_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # If id is not 1 then return abort with 403 error
        if current_user.id != 1:
            return abort(403)
        # Otherwise continue with the route function
        return f(*args, **kwargs)

    return decorated_function


# Register new users into the User database
@app.route('/register', methods=["GET", "POST"])
def register():
    form: RegisterForm = RegisterForm()
    if form.validate_on_submit():

        # Check if user email is already present in the database.
        result = db.session.execute(db.select(User).where(User.email == form.email.data))
        user = result.scalar()
        if user:
            # User already exists
            flash("You've already signed up with that email, log in instead!")
            return redirect(url_for('login'))

        hash_and_salted_password = generate_password_hash(
            form.password.data,
            method='pbkdf2:sha256',
            salt_length=8
        )
        new_user = User(
            email=form.email.data,
            name=form.name.data,
            password=hash_and_salted_password,
        )
        db.session.add(new_user)
        db.session.commit()
        # This line will authenticate the user with Flask-Login
        login_user(new_user)
        return redirect(url_for("get_all_posts"))
    return render_template("register.html", form=form, current_user=current_user)

@app.route('/login', methods=["GET", "POST"])
def login():
    form: LoginForm = LoginForm()
    if form.validate_on_submit():
        password: str = form.password.data
        result: Result = db.session.execute(db.select(User).where(User.email == form.email.data))
        # Note, email in db is unique so will only have one result.
        user: User = result.scalar()
        # Email doesn't exist
        if not user:
            flash("That email does not exist, please try again.")
            return redirect(url_for('login'))
        # Password incorrect
        elif not check_password_hash(user.password, password):
            flash('Password incorrect, please try again.')
            return redirect(url_for('login'))
        else:
            login_user(user)
            return redirect(url_for('get_all_posts'))

    return render_template("login.html", form=form, current_user=current_user)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))


@app.route('/')
def get_all_posts():
    result = db.session.execute(db.select(BlogPost))
    posts = result.scalars().all()
    return render_template("index.html", all_posts=posts, current_user=current_user)


# Add a POST method to be able to post comments
@app.route("/post/<int:post_id>", methods=["GET", "POST"])
def show_post(post_id):
    requested_post = db.get_or_404(BlogPost, post_id)
    # Add the CommentForm to the route
    comment_form: CommentForm = CommentForm()
    # Only allow logged-in users to comment on posts
    if comment_form.validate_on_submit():
        if not current_user.is_authenticated:
            flash("You need to login or register to comment.")
            return redirect(url_for("login"))

        new_comment = Comment(
            text=comment_form.comment_text.data,
            comment_author=current_user,
            parent_post=requested_post
        )
        db.session.add(new_comment)
        db.session.commit()
    gravatar = gravatar_url()
    return render_template("post.html", post=requested_post, current_user=current_user, form=comment_form, gravatar_link=gravatar)


# Use a decorator so only an admin user can create new posts
@app.route("/new-post", methods=["GET", "POST"])
@admin_only
def add_new_post():
    form: CreatePostForm = CreatePostForm()
    if form.validate_on_submit():
        new_post: BlogPost = BlogPost(
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            img_url=form.img_url.data,
            author=current_user,
            date=date.today().strftime("%B %d, %Y")
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=form, current_user=current_user)


# Use a decorator so only an admin user can edit a post 
@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    edit_form: CreatePostForm = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        author=post.author,
        body=post.body
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.author = current_user
        post.body = edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=edit_form, is_edit=True, current_user=current_user)


# Use a decorator so only an admin user can delete a post
@app.route("/delete/<int:post_id>")
@admin_only
def delete_post(post_id):
    post_to_delete: BlogPost = db.get_or_404(BlogPost, post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))


@app.route("/about")
def about():
    return render_template("about.html", current_user=current_user)


@app.route("/contact", methods=["GET", "POST"])
def contact():
    form: ContactForm = ContactForm()
    if form.validate_on_submit():
        name: str = form.name.data
        email: str = form.email.data
        phone: str = form.phone_number.data
        message: str = form.message.data
        
        formatted_message: str = construct_msg(name=name, email=email, phone_number=phone, msg=message)

        try:
            send_email(formatted_message)
            flash("Your message has been sent successfully!", "success")
        except:
            flash("An unexpected error occurred. Please try again later", "danger")

        # Redirect or render a success message after processing the form
        return redirect(url_for("contact"))
    return render_template("contact.html", form=form, current_user=current_user, msg_sent=False)


if __name__ == "__main__":
    app.run(debug=True) 
