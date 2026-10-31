import os

# app.main builds the application as it is imported, and the default environment, production, refuses SQLite.
os.environ["APP_ENVIRONMENT"] = "development"
