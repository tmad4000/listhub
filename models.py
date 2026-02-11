from flask_login import UserMixin


class User(UserMixin):
    def __init__(self, row):
        self.id = row['id']
        self.username = row['username']
        self.display_name = row['display_name']
        self.email = row['email']
        self.password_hash = row['password_hash']
        self.created_at = row['created_at']

    @staticmethod
    def get(db, user_id):
        row = db.execute("SELECT * FROM user WHERE id = ?", (user_id,)).fetchone()
        return User(row) if row else None

    @staticmethod
    def get_by_username(db, username):
        row = db.execute("SELECT * FROM user WHERE username = ?", (username,)).fetchone()
        return User(row) if row else None

    @staticmethod
    def get_by_email(db, email):
        row = db.execute("SELECT * FROM user WHERE email = ?", (email,)).fetchone()
        return User(row) if row else None

    @staticmethod
    def get_by_api_key(db, key_hash):
        row = db.execute(
            "SELECT u.* FROM user u JOIN api_key ak ON u.id = ak.user_id WHERE ak.key_hash = ?",
            (key_hash,)
        ).fetchone()
        return User(row) if row else None
