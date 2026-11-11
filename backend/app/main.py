import csv, hashlib, hmac, io, json, os, re, secrets, smtplib, ssl, time, zipfile
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlencode, urlparse
from cryptography.fernet import Fernet, InvalidToken
import requests
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import JSONResponse
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from itsdangerous import BadSignature
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, delete, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv

load_dotenv()
URL=os.getenv("DATABASE_URL","sqlite:///./classflow.db")
if URL.startswith("postgres://"):URL="postgresql+psycopg://"+URL[len("postgres://"):]
elif URL.startswith("postgresql://"):URL="postgresql+psycopg://"+URL[len("postgresql://"):]
engine=create_engine(URL,connect_args={"check_same_thread":False} if URL.startswith("sqlite") else {},pool_pre_ping=True)
DB=sessionmaker(bind=engine,expire_on_commit=False)
class Base(DeclarativeBase): pass
class User(Base):
 __tablename__="users"
 id:Mapped[int]=mapped_column(primary_key=True); name:Mapped[str]=mapped_column(String(160)); email:Mapped[str]=mapped_column(String(254),unique=True,index=True); pw:Mapped[str]=mapped_column(String(256)); role:Mapped[str]=mapped_column(String(20),index=True); identifier:Mapped[str]=mapped_column(String(80),default=""); department:Mapped[str]=mapped_column(String(120),default=""); grade:Mapped[str]=mapped_column(String(80),default=""); avatar_name:Mapped[str|None]=mapped_column(String(80),nullable=True); approved:Mapped[bool]=mapped_column(Boolean,default=True); email_verified:Mapped[bool]=mapped_column(Boolean,default=True); session_version:Mapped[int]=mapped_column(Integer,default=0); active:Mapped[bool]=mapped_column(Boolean,default=True); created:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class Classroom(Base):
 __tablename__="classes"
 id:Mapped[int]=mapped_column(primary_key=True); name:Mapped[str]=mapped_column(String(160)); subject:Mapped[str]=mapped_column(String(120)); code:Mapped[str]=mapped_column(String(20),unique=True); schedule:Mapped[str]=mapped_column(String(160),default=""); meet:Mapped[str]=mapped_column(String(500),default=""); enrollment_open:Mapped[bool]=mapped_column(Boolean,default=True,server_default="true"); teacher_id:Mapped[int]=mapped_column(ForeignKey("users.id"),index=True); teacher:Mapped[User]=relationship(); enrollments:Mapped[list["Enrollment"]]=relationship(cascade="all, delete-orphan")
class Enrollment(Base):
 __tablename__="enrollments"
 __table_args__=(UniqueConstraint("class_id","student_id"),)
 id:Mapped[int]=mapped_column(primary_key=True); class_id:Mapped[int]=mapped_column(ForeignKey("classes.id",ondelete="CASCADE"),index=True); student_id:Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True)
class Assignment(Base):
 __tablename__="assignments"
 id:Mapped[int]=mapped_column(primary_key=True); class_id:Mapped[int]=mapped_column(ForeignKey("classes.id",ondelete="CASCADE"),index=True); title:Mapped[str]=mapped_column(String(180)); instructions:Mapped[str]=mapped_column(Text); due:Mapped[datetime|None]=mapped_column(DateTime,nullable=True); points:Mapped[int]=mapped_column(Integer,default=100); late:Mapped[bool]=mapped_column(Boolean,default=False); kind:Mapped[str]=mapped_column(String(24),default="assignment")
class Submission(Base):
 __tablename__="submissions"
 __table_args__=(UniqueConstraint("assignment_id","student_id"),)
 id:Mapped[int]=mapped_column(primary_key=True); assignment_id:Mapped[int]=mapped_column(ForeignKey("assignments.id",ondelete="CASCADE"),index=True); student_id:Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True); answer:Mapped[str]=mapped_column(Text,default=""); file_name:Mapped[str]=mapped_column(String(240),default=""); stored_file:Mapped[str|None]=mapped_column(String(80),nullable=True); submitted:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow); score:Mapped[int|None]=mapped_column(Integer,nullable=True); feedback:Mapped[str]=mapped_column(Text,default="")
class Quiz(Base):
 __tablename__="quizzes"
 id:Mapped[int]=mapped_column(primary_key=True); class_id:Mapped[int]=mapped_column(ForeignKey("classes.id",ondelete="CASCADE"),index=True); title:Mapped[str]=mapped_column(String(180)); duration:Mapped[int]=mapped_column(Integer); questions:Mapped[str]=mapped_column(Text)
class Attempt(Base):
 __tablename__="attempts"
 id:Mapped[int]=mapped_column(primary_key=True); quiz_id:Mapped[int]=mapped_column(ForeignKey("quizzes.id",ondelete="CASCADE"),index=True); student_id:Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True); answers:Mapped[str]=mapped_column(Text,default="[]"); started:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow); submitted:Mapped[datetime|None]=mapped_column(DateTime,nullable=True); score:Mapped[int|None]=mapped_column(Integer,nullable=True)
class Attendance(Base):
 __tablename__="attendance"
 __table_args__=(UniqueConstraint("session_id","student_id"),)
 id:Mapped[int]=mapped_column(primary_key=True); class_id:Mapped[int]=mapped_column(ForeignKey("classes.id",ondelete="CASCADE"),index=True); student_id:Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True); teacher_id:Mapped[int]=mapped_column(ForeignKey("users.id")); status:Mapped[str]=mapped_column(String(20)); note:Mapped[str]=mapped_column(String(240),default=""); source:Mapped[str]=mapped_column(String(30),default="teacher"); meeting_id:Mapped[int|None]=mapped_column(ForeignKey("meetings.id",ondelete="SET NULL"),nullable=True); session_id:Mapped[int|None]=mapped_column(ForeignKey("attendance_sessions.id",ondelete="SET NULL"),nullable=True); joined_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True); left_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True); duration_seconds:Mapped[int|None]=mapped_column(Integer,nullable=True); created:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class Audit(Base):
 __tablename__="audit_logs"
 id:Mapped[int]=mapped_column(primary_key=True); actor_id:Mapped[int]=mapped_column(ForeignKey("users.id")); action:Mapped[str]=mapped_column(String(80)); details:Mapped[str]=mapped_column(Text); created:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class Notification(Base):
 __tablename__="notifications"
 id:Mapped[int]=mapped_column(primary_key=True); user_id:Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True); title:Mapped[str]=mapped_column(String(180)); body:Mapped[str]=mapped_column(String(500)); read:Mapped[bool]=mapped_column(Boolean,default=False)
class Announcement(Base):
 __tablename__="announcements"
 id:Mapped[int]=mapped_column(primary_key=True); class_id:Mapped[int]=mapped_column(ForeignKey("classes.id",ondelete="CASCADE"),index=True); teacher_id:Mapped[int]=mapped_column(ForeignKey("users.id")); title:Mapped[str]=mapped_column(String(180)); body:Mapped[str]=mapped_column(Text); priority:Mapped[str]=mapped_column(String(20),default="normal"); created:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class Material(Base):
 __tablename__="materials"
 id:Mapped[int]=mapped_column(primary_key=True); class_id:Mapped[int]=mapped_column(ForeignKey("classes.id",ondelete="CASCADE"),index=True); uploader_id:Mapped[int]=mapped_column(ForeignKey("users.id")); name:Mapped[str]=mapped_column(String(240)); stored_name:Mapped[str]=mapped_column(String(80),unique=True); size:Mapped[int]=mapped_column(Integer); created:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class GoogleCredential(Base):
 __tablename__="google_credentials"
 id:Mapped[int]=mapped_column(primary_key=True); user_id:Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),unique=True); token_ciphertext:Mapped[str]=mapped_column(Text); updated:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class AuthToken(Base):
 __tablename__="auth_tokens"
 id:Mapped[int]=mapped_column(primary_key=True); user_id:Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True); purpose:Mapped[str]=mapped_column(String(24)); token_hash:Mapped[str]=mapped_column(String(64),unique=True); expires:Mapped[datetime]=mapped_column(DateTime); used:Mapped[bool]=mapped_column(Boolean,default=False)
class Message(Base):
 __tablename__="messages"
 id:Mapped[int]=mapped_column(primary_key=True); class_id:Mapped[int]=mapped_column(ForeignKey("classes.id",ondelete="CASCADE"),index=True); sender_id:Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True); recipient_id:Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True); body:Mapped[str]=mapped_column(Text); created:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow); read:Mapped[bool]=mapped_column(Boolean,default=False)
class Meeting(Base):
 __tablename__="meetings"
 id:Mapped[int]=mapped_column(primary_key=True); class_id:Mapped[int]=mapped_column(ForeignKey("classes.id",ondelete="CASCADE"),index=True); creator_id:Mapped[int]=mapped_column(ForeignKey("users.id")); title:Mapped[str]=mapped_column(String(180)); starts:Mapped[datetime]=mapped_column(DateTime); ends:Mapped[datetime]=mapped_column(DateTime); meet_url:Mapped[str]=mapped_column(String(500)); meeting_code:Mapped[str]=mapped_column(String(40)); calendar_event_id:Mapped[str]=mapped_column(String(200)); created:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class MeetingParticipant(Base):
 __tablename__="meeting_participants"
 __table_args__=(UniqueConstraint("meeting_id","participant_ref"),)
 id:Mapped[int]=mapped_column(primary_key=True); meeting_id:Mapped[int]=mapped_column(ForeignKey("meetings.id",ondelete="CASCADE"),index=True); participant_ref:Mapped[str]=mapped_column(String(500)); display_name:Mapped[str]=mapped_column(String(200)); student_id:Mapped[int|None]=mapped_column(ForeignKey("users.id",ondelete="SET NULL"),nullable=True); joined_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True); left_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True); duration_seconds:Mapped[int]=mapped_column(Integer,default=0); confirmed:Mapped[bool]=mapped_column(Boolean,default=False)
class AttendanceSession(Base):
 __tablename__="attendance_sessions"
 id:Mapped[int]=mapped_column(primary_key=True); class_id:Mapped[int]=mapped_column(ForeignKey("classes.id",ondelete="CASCADE"),index=True); teacher_id:Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="CASCADE")); code_hash:Mapped[str]=mapped_column(String(64),unique=True); expires:Mapped[datetime]=mapped_column(DateTime); active:Mapped[bool]=mapped_column(Boolean,default=True); created:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class VirtualRoom(Base):
 __tablename__="virtual_rooms"
 id:Mapped[int]=mapped_column(primary_key=True); class_id:Mapped[int]=mapped_column(ForeignKey("classes.id",ondelete="CASCADE"),index=True); teacher_id:Mapped[int]=mapped_column(ForeignKey("users.id")); title:Mapped[str]=mapped_column(String(180)); active:Mapped[bool]=mapped_column(Boolean,default=True,index=True); created:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow); ended:Mapped[datetime|None]=mapped_column(DateTime,nullable=True); archived:Mapped[bool]=mapped_column(Boolean,default=False,index=True)
class VirtualPresence(Base):
 __tablename__="virtual_presence"
 id:Mapped[int]=mapped_column(primary_key=True); room_id:Mapped[int]=mapped_column(ForeignKey("virtual_rooms.id",ondelete="CASCADE"),index=True); user_id:Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True); joined_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow); last_seen:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow); left_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True); duration_seconds:Mapped[int]=mapped_column(Integer,default=0)
class VirtualSignal(Base):
 __tablename__="virtual_signals"
 id:Mapped[int]=mapped_column(primary_key=True); room_id:Mapped[int]=mapped_column(ForeignKey("virtual_rooms.id",ondelete="CASCADE"),index=True); sender_presence_id:Mapped[int]=mapped_column(ForeignKey("virtual_presence.id",ondelete="CASCADE"),index=True); recipient_presence_id:Mapped[int]=mapped_column(ForeignKey("virtual_presence.id",ondelete="CASCADE"),index=True); payload:Mapped[str]=mapped_column(Text); created:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
UPLOADS=Path(__file__).resolve().parent.parent/"uploads"; UPLOADS.mkdir(exist_ok=True)
app=FastAPI(title="Classflow EMS",version="1.0")
app.state.auth_attempts=defaultdict(deque)
FRONTEND_ORIGIN=os.getenv("FRONTEND_ORIGIN","http://localhost:5173").rstrip("/")
APP_ORIGINS=["http://127.0.0.1:4174","capacitor://localhost","https://localhost"]
EXTRA_CORS_ORIGINS=[origin.strip().rstrip("/") for origin in os.getenv("CORS_ORIGINS","").split(",") if origin.strip()]
ALLOWED_ORIGINS=list(dict.fromkeys([FRONTEND_ORIGIN,*APP_ORIGINS,*EXTRA_CORS_ORIGINS]))
SESSION_SAME_SITE=os.getenv("SESSION_SAME_SITE","lax").lower()
if SESSION_SAME_SITE not in {"lax","strict","none"}:raise RuntimeError("SESSION_SAME_SITE must be lax, strict, or none")
SESSION_MAX_AGE_SECONDS=int(os.getenv("SESSION_MAX_AGE_SECONDS","43200"))
if SESSION_MAX_AGE_SECONDS<60:raise RuntimeError("SESSION_MAX_AGE_SECONDS must be at least 60")
app.add_middleware(SessionMiddleware,secret_key=os.getenv("SECRET_KEY","dev-only-change-me"),session_cookie="classflow_session",same_site=SESSION_SAME_SITE,https_only=os.getenv("COOKIE_SECURE","false").lower()=="true",max_age=SESSION_MAX_AGE_SECONDS)
app.add_middleware(CORSMiddleware,allow_origins=ALLOWED_ORIGINS,allow_credentials=True,allow_methods=["*"],allow_headers=["Content-Type"])
@app.middleware("http")
async def check_request_origin(request, call_next):
 auth_routes={"/api/auth/login","/api/auth/register"}
 if request.url.path in auth_routes:
  key=(request.client.host if request.client else "unknown",request.url.path);now=time.monotonic();events=app.state.auth_attempts.setdefault(key,deque())
  while events and now-events[0]>60:events.popleft()
  if len(events)>=15:return JSONResponse(status_code=429,content={"detail":"Too many attempts; wait a minute and try again"},headers={"Retry-After":"60"})
  events.append(now)
 if request.method in {"POST","PUT","PATCH","DELETE"}:
  origin=request.headers.get("origin")
  if origin:
   normalized_origin=origin.rstrip("/")
   accepted=normalized_origin in ALLOWED_ORIGINS
   if not accepted:
    expected=urlparse(FRONTEND_ORIGIN);actual=urlparse(normalized_origin)
    local_hosts={"localhost","127.0.0.1"}
    accepted=(expected.scheme==actual.scheme=="http" and expected.hostname in local_hosts and actual.hostname in local_hosts and expected.port==actual.port)
   if not accepted:
    forwarded_host=request.headers.get("x-forwarded-host","").split(",")[0].strip()
    forwarded_proto=request.headers.get("x-forwarded-proto","http").split(",")[0].strip()
    accepted=bool(forwarded_host and origin.rstrip("/")==f"{forwarded_proto}://{forwarded_host}".rstrip("/"))
   if not accepted:return JSONResponse(status_code=403,content={"detail":"Request origin is not allowed"})
 response=await call_next(request)
 response.headers["X-Content-Type-Options"]="nosniff";response.headers["X-Frame-Options"]="DENY";response.headers["Referrer-Policy"]="strict-origin-when-cross-origin"
 if os.getenv("COOKIE_SECURE","false").lower()=="true":response.headers["Strict-Transport-Security"]="max-age=31536000; includeSubDomains"
 return response
def dbdep():
 with DB() as db: yield db
def password_hash(p):
 salt=secrets.token_bytes(16);return salt.hex()+"$"+hashlib.pbkdf2_hmac("sha256",p.encode(),salt,310000).hex()
def password_ok(p,h):
 try:
  salt,key=h.split("$");return hmac.compare_digest(hashlib.pbkdf2_hmac("sha256",p.encode(),bytes.fromhex(salt),310000).hex(),key)
 except Exception:return False
def smtp_configured():return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM"))
def send_email(recipient,subject,body):
 if not smtp_configured():raise HTTPException(503,"Email delivery is not configured")
 msg=EmailMessage();msg["Subject"]=subject;msg["From"]=os.environ["SMTP_FROM"];msg["To"]=recipient;msg.set_content(body)
 host=os.environ["SMTP_HOST"];port=int(os.getenv("SMTP_PORT","587"));user=os.getenv("SMTP_USER");password=os.getenv("SMTP_PASSWORD")
 try:
  if os.getenv("SMTP_SSL","false").lower()=="true":
   with smtplib.SMTP_SSL(host,port,context=ssl.create_default_context(),timeout=20) as server:
    if user:server.login(user,password or "")
    server.send_message(msg)
  else:
   with smtplib.SMTP(host,port,timeout=20) as server:
    server.ehlo();server.starttls(context=ssl.create_default_context());server.ehlo()
    if user:server.login(user,password or "")
    server.send_message(msg)
 except (OSError,smtplib.SMTPException):raise HTTPException(502,"Email delivery failed; check SMTP configuration")
def create_auth_token(db,user,purpose,expires_after):
 raw=secrets.token_urlsafe(32);db.add(AuthToken(user_id=user.id,purpose=purpose,token_hash=hashlib.sha256(raw.encode()).hexdigest(),expires=datetime.utcnow()+expires_after,used=False));return raw
GOOGLE_SCOPES=["openid","email","https://www.googleapis.com/auth/calendar.events","https://www.googleapis.com/auth/meetings.space.readonly"]
def google_configured():return all(os.getenv(k) for k in ("GOOGLE_CLIENT_ID","GOOGLE_CLIENT_SECRET","GOOGLE_REDIRECT_URI","GOOGLE_TOKEN_ENCRYPTION_KEY"))
def google_flow(state=None):
 if not google_configured():raise HTTPException(503,"Google integration is not configured")
 config={"web":{"client_id":os.environ["GOOGLE_CLIENT_ID"],"client_secret":os.environ["GOOGLE_CLIENT_SECRET"],"auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token","redirect_uris":[os.environ["GOOGLE_REDIRECT_URI"]]}}
 return Flow.from_client_config(config,scopes=GOOGLE_SCOPES,state=state,redirect_uri=os.environ["GOOGLE_REDIRECT_URI"])
def token_cipher():
 try:return Fernet(os.environ["GOOGLE_TOKEN_ENCRYPTION_KEY"].encode())
 except Exception:raise HTTPException(503,"Google token encryption key is invalid")
def google_credentials(user:User,db:Session):
 if not google_configured():raise HTTPException(503,"Google integration is not configured")
 saved=db.scalar(select(GoogleCredential).where(GoogleCredential.user_id==user.id))
 if not saved:raise HTTPException(409,"Connect your Google account first")
 try:creds=Credentials.from_authorized_user_info(json.loads(token_cipher().decrypt(saved.token_ciphertext.encode())),scopes=GOOGLE_SCOPES)
 except (InvalidToken,ValueError,KeyError):raise HTTPException(500,"Stored Google credentials could not be decrypted")
 if creds.expired and creds.refresh_token:
  try:creds.refresh(GoogleRequest())
  except Exception:raise HTTPException(401,"Google authorization expired; reconnect your account")
  saved.token_ciphertext=token_cipher().encrypt(creds.to_json().encode()).decode();saved.updated=datetime.utcnow();db.commit()
 return creds
def google_get(creds,url,params=None):
 try:
  response=requests.get(url,headers={"Authorization":"Bearer "+creds.token},params=params,timeout=20)
  if response.status_code>=400:raise HTTPException(502,"Google API rejected the request; check enabled APIs and granted scopes")
  return response.json()
 except requests.RequestException:raise HTTPException(502,"Could not reach Google API")
def parse_google_time(value):
 if not value:return None
 return datetime.fromisoformat(value.replace("Z","+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
ALLOWED_UPLOADS={".pdf",".docx",".pptx",".xlsx",".png",".jpg",".jpeg",".webp",".mp4",".mp3",".txt"}
def validate_upload(ext,data):
 if ext==".pdf":return data.startswith(b"%PDF-")
 if ext==".png":return data.startswith(b"\x89PNG\r\n\x1a\n")
 if ext in (".jpg",".jpeg"):return data.startswith(b"\xff\xd8\xff")
 if ext==".webp":return len(data)>=12 and data[:4]==b"RIFF" and data[8:12]==b"WEBP"
 if ext in (".docx",".pptx",".xlsx"):
  required={".docx":"word/document.xml",".pptx":"ppt/presentation.xml",".xlsx":"xl/workbook.xml"}[ext]
  try:
   with zipfile.ZipFile(io.BytesIO(data)) as archive:
    if sum(x.file_size for x in archive.infolist())>100*1024*1024:return False
    return required in archive.namelist()
  except (zipfile.BadZipFile,ValueError):return False
 if ext==".mp4":return len(data)>=12 and data[4:8]==b"ftyp"
 if ext==".mp3":return data.startswith(b"ID3") or (len(data)>1 and data[0]==0xff and data[1]&0xe0==0xe0)
 if ext==".txt":
  try:data.decode("utf-8");return b"\x00" not in data
  except UnicodeDecodeError:return False
 return False
def upload_limit():return int(os.getenv("MAX_UPLOAD_MB","20"))*1024*1024
def me(req:Request,db:Session=Depends(dbdep)):
 u=db.get(User,req.session.get("uid")) if req.session.get("uid") else None
 if not u or req.session.get("sv")!=u.session_version:raise HTTPException(401,"Sign in to continue")
 if not u.active:raise HTTPException(403,"Account is suspended")
 if os.getenv("EMAIL_VERIFICATION_REQUIRED","false").lower()=="true" and not u.email_verified:raise HTTPException(403,"Verify your email before using the platform")
 return u
def roles(*rs):
 def check(u:User=Depends(me)):
  if u.role not in rs:raise HTTPException(403,"Access denied")
  if u.role=="teacher" and not u.approved:raise HTTPException(403,"Teacher approval required")
  return u
 return check
def access(db,u,cid):
 c=db.get(Classroom,cid)
 if not c:raise HTTPException(404,"Class not found")
 if u.role=="admin" or c.teacher_id==u.id or db.scalar(select(Enrollment.id).where(Enrollment.class_id==cid,Enrollment.student_id==u.id)):return c
 raise HTTPException(403,"Not enrolled")
def ud(u):return {"id":u.id,"name":u.name,"email":u.email,"role":u.role,"identifier":u.identifier,"department":u.department,"grade":u.grade,"avatar_url":f"/api/users/{u.id}/avatar?v={u.avatar_name}" if u.avatar_name else None}
def instructor_profile(u):return {"id":u.id,"name":u.name,"role":u.role,"department":u.department,"avatar_url":f"/api/users/{u.id}/avatar?v={u.avatar_name}" if u.avatar_name else None}
def cd(c):return {"id":c.id,"name":c.name,"subject":c.subject,"code":c.code,"schedule":c.schedule,"meet":c.meet,"teacher":c.teacher.name,"instructor":instructor_profile(c.teacher),"students":len(c.enrollments),"enrollment_open":c.enrollment_open}
class Register(BaseModel):
 name:str=Field(min_length=2,max_length=160);email:EmailStr;password:str=Field(min_length=10,max_length=128);role:str="student";identifier:str="";department:str="";grade:str=""
class Login(BaseModel):email:EmailStr;password:str
class ClassInput(BaseModel):name:str=Field(min_length=2,max_length=160);subject:str=Field(min_length=2,max_length=120);schedule:str=Field(default="",max_length=160);meet:str=Field(default="",max_length=500)
class EnrollmentToggle(BaseModel):open:bool
class AssignmentInput(BaseModel):title:str;instructions:str;due:datetime|None=None;points:int=Field(default=100,ge=1,le=10000);late:bool=False
class SubmissionInput(BaseModel):answer:str=""
class QuizInput(BaseModel):title:str;duration:int=Field(ge=1,le=300);questions:list[dict]
class AttemptInput(BaseModel):answers:list[str]=Field(default_factory=list);submit:bool=False
class AttendanceInput(BaseModel):student_id:int;status:str;note:str=""
class AttendanceCodeInput(BaseModel):code:str=Field(min_length=12,max_length=128)
class AnnouncementInput(BaseModel):title:str;body:str;priority:str="normal"
class VirtualRoomInput(BaseModel):title:str=Field(min_length=2,max_length=180)
class VirtualPresenceInput(BaseModel):presence_id:int
class VirtualSignalInput(BaseModel):sender_presence_id:int;recipient_presence_id:int;payload:dict
class MeetingInput(BaseModel):title:str;starts:datetime;ends:datetime
class ConfirmParticipantInput(BaseModel):student_id:int
class TokenInput(BaseModel):token:str
class ForgotInput(BaseModel):email:EmailStr
class ResetInput(BaseModel):token:str;password:str=Field(min_length=10,max_length=128)
class ProfileInput(BaseModel):name:str=Field(min_length=2,max_length=160);identifier:str="";department:str="";grade:str=""
class MessageInput(BaseModel):recipient_id:int;body:str=Field(min_length=1,max_length=5000)
@app.get("/api/health")
def health():return {"status":"ok","service":"Classflow"}
@app.post("/api/auth/register")
def register(d:Register,r:Request,db:Session=Depends(dbdep)):
 role=d.role.lower();email=str(d.email).lower()
 if role not in ("student","teacher"):raise HTTPException(400,"Choose student or teacher")
 verify_required=os.getenv("EMAIL_VERIFICATION_REQUIRED","false").lower()=="true"
 if verify_required and not smtp_configured():raise HTTPException(503,"Email verification is enabled but SMTP is not configured")
 if db.scalar(select(User.id).where(User.email==email)):raise HTTPException(409,"Email already exists")
 admin=email==os.getenv("ADMIN_EMAIL","")
 u=User(name=d.name.strip(),email=email,pw=password_hash(d.password),role="admin" if admin else role,identifier=d.identifier[:80],department=d.department[:120],grade=d.grade[:80],approved=role!="teacher",email_verified=not verify_required)
 db.add(u);db.commit();db.refresh(u)
 if verify_required:
  token=create_auth_token(db,u,"verify",timedelta(hours=24));db.commit();send_email(u.email,"Verify your Classflow email",os.getenv("FRONTEND_ORIGIN","http://localhost:5173")+"/?verify_token="+token+"\n\nThis link expires in 24 hours.")
  return {"requires_verification":True,"message":"Check your email to verify your account."}
 r.session["uid"]=u.id;r.session["sv"]=u.session_version;return ud(u)
@app.post("/api/auth/login")
def login(d:Login,r:Request,db:Session=Depends(dbdep)):
 u=db.scalar(select(User).where(User.email==str(d.email).lower()))
 if not u or not password_ok(d.password,u.pw):raise HTTPException(401,"Email or password is incorrect")
 if not u.active:raise HTTPException(403,"Account is suspended")
 if os.getenv("EMAIL_VERIFICATION_REQUIRED","false").lower()=="true" and not u.email_verified:raise HTTPException(403,"Verify your email before signing in")
 if u.role=="teacher" and not u.approved:raise HTTPException(403,"Teacher approval required")
 r.session.clear();r.session["uid"]=u.id;r.session["sv"]=u.session_version;return ud(u)
def oauth_callback_url(provider:str,request:Request)->str:
 configured=os.getenv(provider.upper()+"_AUTH_REDIRECT_URI","").strip()
 return configured or str(request.base_url).rstrip("/")+"/api/auth/oauth/"+provider+"/callback"
@app.get("/api/auth/oauth/providers")
def oauth_providers():
 return {"google":bool(os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET")),"facebook":bool(os.getenv("FACEBOOK_CLIENT_ID") and os.getenv("FACEBOOK_CLIENT_SECRET"))}
@app.get("/api/auth/oauth/{provider}/start")
def oauth_start(provider:str,request:Request):
 if provider not in ("google","facebook"):raise HTTPException(404,"Sign-in provider not found")
 client_id=os.getenv(provider.upper()+"_CLIENT_ID");client_secret=os.getenv(provider.upper()+"_CLIENT_SECRET")
 if not client_id or not client_secret:raise HTTPException(503,provider.title()+" sign-in is not configured on this server")
 state=secrets.token_urlsafe(32);request.session["social_oauth_state"]=state;request.session["social_oauth_provider"]=provider
 redirect_uri=oauth_callback_url(provider,request)
 if provider=="google":
  config={"web":{"client_id":client_id,"client_secret":client_secret,"auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token","redirect_uris":[redirect_uri]}}
  flow=Flow.from_client_config(config,scopes=["openid","email","profile"],state=state,redirect_uri=redirect_uri)
  authorization_url,_=flow.authorization_url(prompt="select_account")
 else:
  authorization_url="https://www.facebook.com/dialog/oauth?"+urlencode({"client_id":client_id,"redirect_uri":redirect_uri,"state":state,"scope":"email,public_profile","response_type":"code"})
 return {"authorization_url":authorization_url}
@app.get("/api/auth/oauth/{provider}/callback")
def oauth_callback(provider:str,request:Request,code:str|None=None,state:str|None=None,error:str|None=None,db:Session=Depends(dbdep)):
 expected_state=request.session.pop("social_oauth_state",None);expected_provider=request.session.pop("social_oauth_provider",None)
 if not expected_state or not state or not secrets.compare_digest(expected_state,state) or expected_provider!=provider:raise HTTPException(400,"Sign-in request expired. Please try again.")
 if error or not code:raise HTTPException(400,"Sign-in was cancelled or the provider returned an error.")
 client_id=os.getenv(provider.upper()+"_CLIENT_ID","");client_secret=os.getenv(provider.upper()+"_CLIENT_SECRET","")
 if not client_id or not client_secret:raise HTTPException(503,provider.title()+" sign-in is not configured on this server")
 redirect_uri=oauth_callback_url(provider,request)
 try:
  if provider=="google":
   config={"web":{"client_id":client_id,"client_secret":client_secret,"auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token","redirect_uris":[redirect_uri]}}
   flow=Flow.from_client_config(config,scopes=["openid","email","profile"],state=state,redirect_uri=redirect_uri);flow.fetch_token(code=code)
   from google.oauth2 import id_token
   claims=id_token.verify_oauth2_token(flow.credentials.id_token,GoogleRequest(),client_id)
   if not claims.get("email_verified"):raise HTTPException(403,"Verify your Google email address before signing in.")
   email=str(claims["email"]).lower();name=str(claims.get("name") or email.split("@")[0])
  elif provider=="facebook":
   token_response=requests.get("https://graph.facebook.com/oauth/access_token",params={"client_id":client_id,"client_secret":client_secret,"redirect_uri":redirect_uri,"code":code},timeout=15)
   token_response.raise_for_status();access_token=token_response.json().get("access_token")
   if not access_token:raise HTTPException(401,"Facebook did not return an access token.")
   profile_response=requests.get("https://graph.facebook.com/me",params={"fields":"id,name,email","access_token":access_token},timeout=15)
   profile_response.raise_for_status();profile=profile_response.json()
   if not profile.get("email"):raise HTTPException(403,"Facebook did not share a verified email. Allow email access and try again.")
   email=str(profile["email"]).lower();name=str(profile.get("name") or email.split("@")[0])
  else:raise HTTPException(404,"Sign-in provider not found")
 except HTTPException:raise
 except (requests.RequestException,ValueError,KeyError) as failure:raise HTTPException(502,provider.title()+" sign-in could not be verified. Please try again.") from failure
 user=db.scalar(select(User).where(User.email==email))
 if not user:
  user=User(name=name[:160],email=email,pw=password_hash(secrets.token_urlsafe(48)),role="student",approved=True,email_verified=True)
  db.add(user);db.commit();db.refresh(user)
 if not user.active:raise HTTPException(403,"Account is suspended")
 if user.role=="teacher" and not user.approved:raise HTTPException(403,"Teacher approval required")
 request.session.clear();request.session["uid"]=user.id;request.session["sv"]=user.session_version
 return RedirectResponse(FRONTEND_ORIGIN+"?oauth=success")
@app.post("/api/auth/logout")
def logout(r:Request):r.session.clear();return {"ok":True}
@app.get("/api/auth/me")
def auth_me(u:User=Depends(me)):return ud(u)
@app.put("/api/profile")
def update_profile(d:ProfileInput,u:User=Depends(me),db:Session=Depends(dbdep)):
 u.name=d.name.strip();u.identifier=d.identifier[:80];u.department=d.department[:120];u.grade=d.grade[:80];db.commit();return ud(u)
@app.post("/api/profile/avatar")
async def upload_avatar(file:UploadFile=File(...),u:User=Depends(me),db:Session=Depends(dbdep)):
 ext=Path(file.filename or "").suffix.lower()
 if ext not in (".png",".jpg",".jpeg",".webp"):raise HTTPException(415,"Choose a PNG, JPEG, or WebP image")
 data=await file.read(3*1024*1024+1)
 if len(data)>3*1024*1024:raise HTTPException(413,"Profile pictures must be 3 MB or smaller")
 if not validate_upload(ext,data):raise HTTPException(415,"Image content does not match its file type")
 avatar_dir=UPLOADS/"avatars";avatar_dir.mkdir(exist_ok=True)
 stored=f"{u.id}-{secrets.token_hex(16)}{ext}"; (avatar_dir/stored).write_bytes(data)
 previous=u.avatar_name;u.avatar_name=stored;db.commit()
 if previous:(avatar_dir/previous).unlink(missing_ok=True)
 return ud(u)
@app.get("/api/users/{uid}/avatar")
def get_avatar(uid:int,u:User=Depends(me),db:Session=Depends(dbdep)):
 target=db.get(User,uid)
 if not target or not target.avatar_name:raise HTTPException(404,"Profile picture not found")
 path=UPLOADS/"avatars"/target.avatar_name
 if not path.is_file():raise HTTPException(404,"Profile picture not found")
 media={".png":"image/png",".jpg":"image/jpeg",".jpeg":"image/jpeg",".webp":"image/webp"}[Path(target.avatar_name).suffix.lower()]
 return FileResponse(path,media_type=media,headers={"Cache-Control":"private, max-age=3600"})
@app.post("/api/auth/verify-email")
def verify_email(d:TokenInput,db:Session=Depends(dbdep)):
 token=db.scalar(select(AuthToken).where(AuthToken.token_hash==hashlib.sha256(d.token.encode()).hexdigest(),AuthToken.purpose=="verify",AuthToken.used==False))
 if not token or token.expires<datetime.utcnow():raise HTTPException(400,"Verification link is invalid or expired")
 user=db.get(User,token.user_id);user.email_verified=True;token.used=True;db.commit();return {"ok":True,"message":"Email verified. You can sign in."}
@app.post("/api/auth/resend-verification")
def resend_verification(d:ForgotInput,db:Session=Depends(dbdep)):
 if os.getenv("EMAIL_VERIFICATION_REQUIRED","false").lower()=="true" and smtp_configured():
  user=db.scalar(select(User).where(User.email==str(d.email).lower()))
  if user and not user.email_verified:
   token=create_auth_token(db,user,"verify",timedelta(hours=24));db.commit();send_email(user.email,"Verify your Classflow email",os.getenv("FRONTEND_ORIGIN","http://localhost:5173")+"/?verify_token="+token+"\n\nThis link expires in 24 hours.")
 return {"ok":True,"message":"If the account needs verification, an email has been sent."}
@app.post("/api/auth/forgot-password")
def forgot_password(d:ForgotInput,db:Session=Depends(dbdep)):
 user=db.scalar(select(User).where(User.email==str(d.email).lower()))
 if user and smtp_configured():
  token=create_auth_token(db,user,"reset",timedelta(minutes=30));db.commit();send_email(user.email,"Reset your Classflow password",os.getenv("FRONTEND_ORIGIN","http://localhost:5173")+"/?reset_token="+token+"\n\nThis link expires in 30 minutes. If you did not request this, ignore this message.")
 return {"ok":True,"message":"If that account exists, a reset link has been sent."}
@app.post("/api/auth/reset-password")
def reset_password(d:ResetInput,db:Session=Depends(dbdep)):
 token=db.scalar(select(AuthToken).where(AuthToken.token_hash==hashlib.sha256(d.token.encode()).hexdigest(),AuthToken.purpose=="reset",AuthToken.used==False))
 if not token or token.expires<datetime.utcnow():raise HTTPException(400,"Reset link is invalid or expired")
 user=db.get(User,token.user_id);user.pw=password_hash(d.password);user.session_version+=1;token.used=True;db.commit();return {"ok":True,"message":"Password updated. Sign in with your new password."}
@app.get("/api/dashboard")
def dashboard(u:User=Depends(me),db:Session=Depends(dbdep)):
 if u.role=="admin":return {"user":ud(u),"stats":{"users":len(db.scalars(select(User.id)).all()),"pending":len(db.scalars(select(User.id).where(User.role=="teacher",User.approved==False)).all()),"classes":len(db.scalars(select(Classroom.id)).all())},"classes":[cd(c) for c in db.scalars(select(Classroom)).all()],"assignments":[],"notifications":[]}
 cs=db.scalars(select(Classroom).where(Classroom.teacher_id==u.id)).all() if u.role=="teacher" else db.scalars(select(Classroom).join(Enrollment).where(Enrollment.student_id==u.id)).all()
 ids=[c.id for c in cs];aa=db.scalars(select(Assignment).where(Assignment.class_id.in_(ids)).order_by(Assignment.id.desc()).limit(10)).all() if ids else []
 ns=db.scalars(select(Notification).where(Notification.user_id==u.id).order_by(Notification.id.desc()).limit(8)).all()
 pending=sum(bool(not db.scalar(select(Submission.id).where(Submission.assignment_id==a.id,Submission.student_id==u.id))) for a in aa) if u.role=="student" else 0
 return {"user":ud(u),"stats":{"classes":len(cs),"assignments":len(aa),"pending":pending},"classes":[cd(c) for c in cs],"assignments":[{"id":a.id,"title":a.title,"class_id":a.class_id,"due":a.due.isoformat() if a.due else None,"points":a.points} for a in aa],"notifications":[{"id":n.id,"title":n.title,"body":n.body,"read":n.read} for n in ns]}
@app.get("/api/classes")
def classes(u:User=Depends(me),db:Session=Depends(dbdep)):
 cs=db.scalars(select(Classroom)).all() if u.role=="admin" else db.scalars(select(Classroom).where(Classroom.teacher_id==u.id)).all() if u.role=="teacher" else db.scalars(select(Classroom).join(Enrollment).where(Enrollment.student_id==u.id)).all()
 return [cd(c) for c in cs]
@app.post("/api/classes")
def create_class(d:ClassInput,u:User=Depends(roles("teacher","admin")),db:Session=Depends(dbdep)):
 c=Classroom(name=d.name[:160],subject=d.subject[:120],schedule=d.schedule[:160],meet=d.meet[:500],code=secrets.token_hex(3).upper(),teacher_id=u.id);db.add(c);db.commit();db.refresh(c);return cd(c)
@app.delete("/api/classes/{cid}")
def delete_class(cid:int,u:User=Depends(roles("teacher","admin")),db:Session=Depends(dbdep)):
 c=db.get(Classroom,cid)
 if not c:raise HTTPException(404,"Class not found")
 if u.role=="teacher" and c.teacher_id!=u.id:raise HTTPException(403,"Only the class teacher can delete this class")
 assignment_ids=db.scalars(select(Assignment.id).where(Assignment.class_id==cid)).all()
 quiz_ids=db.scalars(select(Quiz.id).where(Quiz.class_id==cid)).all()
 meeting_ids=db.scalars(select(Meeting.id).where(Meeting.class_id==cid)).all()
 room_ids=db.scalars(select(VirtualRoom.id).where(VirtualRoom.class_id==cid)).all()
 material_files=db.scalars(select(Material.stored_name).where(Material.class_id==cid)).all()
 submission_files=db.scalars(select(Submission.stored_file).where(Submission.assignment_id.in_(assignment_ids),Submission.stored_file.is_not(None))).all() if assignment_ids else []
 if assignment_ids:db.execute(delete(Submission).where(Submission.assignment_id.in_(assignment_ids)))
 if quiz_ids:db.execute(delete(Attempt).where(Attempt.quiz_id.in_(quiz_ids)))
 if meeting_ids:db.execute(delete(MeetingParticipant).where(MeetingParticipant.meeting_id.in_(meeting_ids)))
 if room_ids:
  db.execute(delete(VirtualSignal).where(VirtualSignal.room_id.in_(room_ids)))
  db.execute(delete(VirtualPresence).where(VirtualPresence.room_id.in_(room_ids)))
  db.execute(delete(VirtualRoom).where(VirtualRoom.id.in_(room_ids)))
 db.execute(delete(Enrollment).where(Enrollment.class_id==cid))
 db.execute(delete(Assignment).where(Assignment.class_id==cid))
 db.execute(delete(Quiz).where(Quiz.class_id==cid))
 db.execute(delete(Attendance).where(Attendance.class_id==cid))
 db.execute(delete(Announcement).where(Announcement.class_id==cid))
 db.execute(delete(Material).where(Material.class_id==cid))
 db.execute(delete(Message).where(Message.class_id==cid))
 db.execute(delete(Meeting).where(Meeting.class_id==cid))
 db.execute(delete(AttendanceSession).where(AttendanceSession.class_id==cid))
 db.add(Audit(actor_id=u.id,action="class.deleted",details=f"Class {cid}; {c.name}"))
 db.delete(c);db.commit()
 for stored_name in [*material_files,*submission_files]:(UPLOADS/stored_name).unlink(missing_ok=True)
 return {"ok":True}
@app.get("/api/classes/available")
def available_classes(u:User=Depends(roles("student")),db:Session=Depends(dbdep)):
 enrolled=set(db.scalars(select(Enrollment.class_id).where(Enrollment.student_id==u.id)).all())
 return [{"id":c.id,"name":c.name,"subject":c.subject,"schedule":c.schedule,"teacher":c.teacher.name,"instructor":instructor_profile(c.teacher),"students":len(c.enrollments)} for c in db.scalars(select(Classroom).where(Classroom.enrollment_open==True)).all() if c.id not in enrolled]
@app.post("/api/classes/{cid}/join")
def join_available_class(cid:int,u:User=Depends(roles("student")),db:Session=Depends(dbdep)):
 c=db.get(Classroom,cid)
 if not c:raise HTTPException(404,"Class not found")
 if not c.enrollment_open:raise HTTPException(409,"Enrollment for this class is closed")
 if not db.scalar(select(Enrollment.id).where(Enrollment.class_id==c.id,Enrollment.student_id==u.id)):
  db.add(Enrollment(class_id=c.id,student_id=u.id));db.add(Notification(user_id=c.teacher_id,title="New student",body=f"{u.name} joined {c.name}"));db.commit()
 return cd(c)
@app.put("/api/classes/{cid}/enrollment")
def toggle_class_enrollment(cid:int,d:EnrollmentToggle,u:User=Depends(roles("teacher","admin")),db:Session=Depends(dbdep)):
 c=db.get(Classroom,cid)
 if not c:raise HTTPException(404,"Class not found")
 if u.role=="teacher" and c.teacher_id!=u.id:raise HTTPException(403,"Only the class teacher can change enrollment")
 c.enrollment_open=d.open;db.commit();return {"open":c.enrollment_open}
@app.post("/api/classes/join/{code}")
def join(code:str,u:User=Depends(roles("student")),db:Session=Depends(dbdep)):
 c=db.scalar(select(Classroom).where(Classroom.code==code.upper()))
 if not c:raise HTTPException(404,"Class code not found")
 if not c.enrollment_open:raise HTTPException(409,"Enrollment for this class is closed")
 if not db.scalar(select(Enrollment.id).where(Enrollment.class_id==c.id,Enrollment.student_id==u.id)):
  db.add(Enrollment(class_id=c.id,student_id=u.id));db.add(Notification(user_id=c.teacher_id,title="New student",body=f"{u.name} joined {c.name}"));db.commit()
 return cd(c)
@app.get("/api/classes/{cid}/assignments")
def assignments(cid:int,u:User=Depends(me),db:Session=Depends(dbdep)):
 access(db,u,cid);out=[]
 for a in db.scalars(select(Assignment).where(Assignment.class_id==cid,Assignment.kind=="assignment").order_by(Assignment.id.desc())).all():
  s=db.scalar(select(Submission).where(Submission.assignment_id==a.id,Submission.student_id==u.id)) if u.role=="student" else None
  subs=[]
  if u.role in ("teacher","admin"):
   for sub,student in db.execute(select(Submission,User).join(User,User.id==Submission.student_id).where(Submission.assignment_id==a.id)).all():subs.append({"id":sub.id,"student":student.name,"answer":sub.answer,"file_name":sub.file_name,"download_url":f"/api/submissions/{sub.id}/download" if sub.stored_file else None,"score":sub.score,"feedback":sub.feedback})
  out.append({"id":a.id,"title":a.title,"instructions":a.instructions,"due":a.due.isoformat() if a.due else None,"points":a.points,"late":a.late,"submission":{"id":s.id,"answer":s.answer,"file_name":s.file_name,"download_url":f"/api/submissions/{s.id}/download" if s.stored_file else None,"score":s.score,"feedback":s.feedback} if s else None,"submissions":subs})
 return out
@app.post("/api/classes/{cid}/assignments")
def add_assignment(cid:int,d:AssignmentInput,u:User=Depends(roles("teacher","admin")),db:Session=Depends(dbdep)):
 c=access(db,u,cid)
 if u.role=="teacher" and c.teacher_id!=u.id:raise HTTPException(403,"Only class teacher can publish")
 a=Assignment(class_id=cid,title=d.title[:180],instructions=d.instructions,due=d.due,points=d.points,late=d.late);db.add(a);db.flush()
 for e in c.enrollments:db.add(Notification(user_id=e.student_id,title="New assignment",body=f"{a.title} added to {c.name}"))
 db.commit();return {"id":a.id,"title":a.title}
@app.get("/api/classes/{cid}/activities")
def activities(cid:int,u:User=Depends(me),db:Session=Depends(dbdep)):
 access(db,u,cid);out=[]
 for a in db.scalars(select(Assignment).where(Assignment.class_id==cid,Assignment.kind=="activity").order_by(Assignment.id.desc())).all():
  s=db.scalar(select(Submission).where(Submission.assignment_id==a.id,Submission.student_id==u.id)) if u.role=="student" else None
  out.append({"id":a.id,"title":a.title,"instructions":a.instructions,"due":a.due.isoformat() if a.due else None,"points":a.points,"submission":{"id":s.id,"answer":s.answer,"score":s.score} if s else None})
 return out
@app.post("/api/classes/{cid}/activities")
def create_activity(cid:int,d:AssignmentInput,u:User=Depends(roles("teacher","admin")),db:Session=Depends(dbdep)):
 c=access(db,u,cid)
 if u.role=="teacher" and c.teacher_id!=u.id:raise HTTPException(403,"Only class teacher can publish")
 a=Assignment(class_id=cid,title=d.title[:180],instructions=d.instructions,due=d.due,points=d.points,late=d.late,kind="activity");db.add(a);db.flush()
 for e in c.enrollments:db.add(Notification(user_id=e.student_id,title="New activity",body=f"{a.title} was added to {c.name}."))
 db.commit();return {"id":a.id,"title":a.title}
@app.post("/api/activities/{aid}/submit")
def submit_activity(aid:int,d:SubmissionInput,u:User=Depends(roles("student")),db:Session=Depends(dbdep)):
 a=db.get(Assignment,aid)
 if not a or a.kind!="activity":raise HTTPException(404,"Activity not found")
 return submit(aid,d,u,db)
@app.get("/api/classes/{cid}/contacts")
def class_contacts(cid:int,u:User=Depends(me),db:Session=Depends(dbdep)):
 c=access(db,u,cid)
 if u.role=="student":return [ud(c.teacher)]
 return [ud(db.get(User,e.student_id)) for e in c.enrollments]
def authorized_peer(db,user,classroom,peer_id):
 if user.id==peer_id:raise HTTPException(400,"Choose another participant")
 if user.role=="student":valid=peer_id==classroom.teacher_id
 elif user.role=="teacher":valid=classroom.teacher_id==user.id and bool(db.scalar(select(Enrollment.id).where(Enrollment.class_id==classroom.id,Enrollment.student_id==peer_id)))
 else:valid=peer_id==classroom.teacher_id or bool(db.scalar(select(Enrollment.id).where(Enrollment.class_id==classroom.id,Enrollment.student_id==peer_id)))
 if not valid:raise HTTPException(403,"Private messages are limited to your class teacher and enrolled students")
 peer=db.get(User,peer_id)
 if not peer or not peer.active:raise HTTPException(404,"Participant not found")
 return peer
@app.get("/api/classes/{cid}/messages")
def list_messages(cid:int,peer_id:int,u:User=Depends(me),db:Session=Depends(dbdep)):
 c=access(db,u,cid);peer=authorized_peer(db,u,c,peer_id)
 rows=db.scalars(select(Message).where(Message.class_id==cid,((Message.sender_id==u.id)&(Message.recipient_id==peer.id))|((Message.sender_id==peer.id)&(Message.recipient_id==u.id))).order_by(Message.created.desc()).limit(100)).all()
 for item in rows:
  if item.recipient_id==u.id:item.read=True
 db.commit()
 return [{"id":m.id,"sender_id":m.sender_id,"sender":db.get(User,m.sender_id).name,"body":m.body,"created":m.created.isoformat(),"read":m.read} for m in reversed(rows)]
@app.post("/api/classes/{cid}/messages")
def send_message(cid:int,d:MessageInput,u:User=Depends(me),db:Session=Depends(dbdep)):
 c=access(db,u,cid);peer=authorized_peer(db,u,c,d.recipient_id)
 msg=Message(class_id=cid,sender_id=u.id,recipient_id=peer.id,body=d.body.strip()[:5000]);db.add(msg);db.add(Notification(user_id=peer.id,title="New class message",body=f"{u.name}: {msg.body[:400]}"));db.commit();db.refresh(msg)
 return {"id":msg.id,"created":msg.created.isoformat()}
@app.post("/api/assignments/{aid}/submit")
def submit(aid:int,d:SubmissionInput,u:User=Depends(roles("student")),db:Session=Depends(dbdep)):
 a=db.get(Assignment,aid)
 if not a:raise HTTPException(404,"Assignment not found")
 access(db,u,a.class_id)
 now=datetime.now(a.due.tzinfo) if a.due and a.due.tzinfo else datetime.utcnow()
 if a.due and now>a.due and not a.late:raise HTTPException(409,"Deadline passed")
 s=db.scalar(select(Submission).where(Submission.assignment_id==aid,Submission.student_id==u.id))
 if not s:s=Submission(assignment_id=aid,student_id=u.id);db.add(s)
 s.answer=d.answer[:50000];s.submitted=datetime.utcnow();db.commit();return {"id":s.id,"submitted":s.submitted.isoformat()}
@app.post("/api/assignments/{aid}/upload")
async def upload_submission(aid:int,file:UploadFile=File(...),u:User=Depends(roles("student")),db:Session=Depends(dbdep)):
 a=db.get(Assignment,aid)
 if not a:raise HTTPException(404,"Assignment not found")
 access(db,u,a.class_id)
 now=datetime.now(a.due.tzinfo) if a.due and a.due.tzinfo else datetime.utcnow()
 if a.due and now>a.due and not a.late:raise HTTPException(409,"Deadline passed")
 ext=Path(file.filename or "").suffix.lower()
 if ext not in ALLOWED_UPLOADS:raise HTTPException(415,"File type is not allowed")
 data=await file.read(upload_limit()+1)
 if len(data)>upload_limit():raise HTTPException(413,"File exceeds the upload limit")
 if not validate_upload(ext,data):raise HTTPException(415,"File content does not match the selected file type")
 stored=secrets.token_hex(20)+ext;(UPLOADS/stored).write_bytes(data)
 sub=db.scalar(select(Submission).where(Submission.assignment_id==aid,Submission.student_id==u.id))
 if not sub:sub=Submission(assignment_id=aid,student_id=u.id);db.add(sub)
 previous=sub.stored_file;sub.stored_file=stored;sub.file_name=Path(file.filename or "submission").name[:240];sub.submitted=datetime.utcnow();db.commit()
 if previous:(UPLOADS/previous).unlink(missing_ok=True)
 return {"id":sub.id,"file_name":sub.file_name,"submitted":sub.submitted.isoformat()}
@app.get("/api/submissions/{sid}/download")
def download_submission(sid:int,u:User=Depends(me),db:Session=Depends(dbdep)):
 sub=db.get(Submission,sid)
 if not sub or not sub.stored_file:raise HTTPException(404,"Submission file not found")
 if u.role=="student" and sub.student_id!=u.id:raise HTTPException(404,"Submission file not found")
 assignment=db.get(Assignment,sub.assignment_id);c=access(db,u,assignment.class_id)
 if u.role=="teacher" and c.teacher_id!=u.id:raise HTTPException(403,"Forbidden")
 path=UPLOADS/sub.stored_file
 if not path.is_file():raise HTTPException(404,"Submission file not found")
 return FileResponse(path,filename=sub.file_name)
@app.get("/api/classes/{cid}/submissions")
def submissions(cid:int,u:User=Depends(roles("teacher","admin")),db:Session=Depends(dbdep)):
 c=access(db,u,cid)
 if u.role=="teacher" and c.teacher_id!=u.id:raise HTTPException(403,"Forbidden")
 rows=db.execute(select(Submission,Assignment,User).join(Assignment).join(User,User.id==Submission.student_id).where(Assignment.class_id==cid)).all()
 return [{"id":s.id,"assignment":a.title,"student":st.name,"answer":s.answer,"file_name":s.file_name,"download_url":f"/api/submissions/{s.id}/download" if s.stored_file else None,"submitted":s.submitted.isoformat(),"score":s.score,"feedback":s.feedback} for s,a,st in rows]
@app.put("/api/submissions/{sid}/grade")
def grade(sid:int,d:dict,u:User=Depends(roles("teacher","admin")),db:Session=Depends(dbdep)):
 s=db.get(Submission,sid)
 if not s:raise HTTPException(404,"Submission not found")
 a=db.get(Assignment,s.assignment_id);c=access(db,u,a.class_id)
 if u.role=="teacher" and c.teacher_id!=u.id:raise HTTPException(403,"Forbidden")
 score=int(d.get("score",-1))
 if score<0 or score>a.points:raise HTTPException(400,"Score outside allowed range")
 s.score=score;s.feedback=str(d.get("feedback",""))[:5000];db.add(Notification(user_id=s.student_id,title="Grade published",body=f"{a.title}: {score}/{a.points}"));db.commit();return {"ok":True}
@app.post("/api/classes/{cid}/quizzes")
def add_quiz(cid:int,d:QuizInput,u:User=Depends(roles("teacher","admin")),db:Session=Depends(dbdep)):
 c=access(db,u,cid)
 if u.role=="teacher" and c.teacher_id!=u.id:raise HTTPException(403,"Forbidden")
 if not 1<=len(d.questions)<=100:raise HTTPException(400,"Quiz needs 1–100 questions")
 for q in d.questions:
  if not q.get("prompt") or len(q.get("choices",[]))<2 or not isinstance(q.get("answer"),int) or q["answer"] not in range(len(q["choices"])):raise HTTPException(400,"Question needs prompt, choices and correct answer")
 quiz=Quiz(class_id=cid,title=d.title[:180],duration=d.duration,questions=json.dumps(d.questions));db.add(quiz);db.flush()
 for e in c.enrollments:db.add(Notification(user_id=e.student_id,title="New quiz",body=f"{quiz.title} in {c.name}"))
 db.commit();return {"id":quiz.id,"title":quiz.title}
@app.get("/api/classes/{cid}/quizzes")
def quizzes(cid:int,u:User=Depends(me),db:Session=Depends(dbdep)):
 access(db,u,cid);rows=db.scalars(select(Quiz).where(Quiz.class_id==cid)).all()
 return [{"id":q.id,"title":q.title,"duration":q.duration,"questions":json.loads(q.questions) if u.role!="student" else [{"prompt":x["prompt"],"choices":x["choices"]} for x in json.loads(q.questions)]} for q in rows]
@app.post("/api/quizzes/{qid}/attempt")
def attempt(qid:int,d:AttemptInput,u:User=Depends(roles("student")),db:Session=Depends(dbdep)):
 q=db.get(Quiz,qid)
 if not q:raise HTTPException(404,"Quiz not found")
 access(db,u,q.class_id);now=datetime.utcnow();row=db.scalar(select(Attempt).where(Attempt.quiz_id==qid,Attempt.student_id==u.id,Attempt.submitted.is_(None)))
 if not row:row=Attempt(quiz_id=qid,student_id=u.id);db.add(row);db.flush()
 if row.submitted:raise HTTPException(409,"Attempt submitted")
 qs=json.loads(q.questions);row.answers=json.dumps(d.answers)
 if d.submit or now>row.started+timedelta(minutes=q.duration):
  row.submitted=now;row.score=sum(1 for i,x in enumerate(qs) if i<len(d.answers) and d.answers[i].isdigit() and int(d.answers[i])==x["answer"])
 db.commit();return {"id":row.id,"submitted":bool(row.submitted),"score":row.score,"deadline":(row.started+timedelta(minutes=q.duration)).isoformat()+"Z","answers":d.answers}
@app.get("/api/classes/{cid}/students")
def students(cid:int,u:User=Depends(roles("teacher","admin")),db:Session=Depends(dbdep)):
 c=access(db,u,cid)
 if u.role=="teacher" and c.teacher_id!=u.id:raise HTTPException(403,"Forbidden")
 return [ud(db.get(User,e.student_id)) for e in c.enrollments]
@app.post("/api/classes/{cid}/attendance")
def mark(cid:int,d:AttendanceInput,u:User=Depends(roles("teacher","admin")),db:Session=Depends(dbdep)):
 c=access(db,u,cid)
 if u.role=="teacher" and c.teacher_id!=u.id:raise HTTPException(403,"Forbidden")
 if d.status not in ("present","late","absent","excused"):raise HTTPException(400,"Invalid status")
 if not db.scalar(select(Enrollment.id).where(Enrollment.class_id==cid,Enrollment.student_id==d.student_id)):raise HTTPException(400,"Student not enrolled")
 x=Attendance(class_id=cid,student_id=d.student_id,teacher_id=u.id,status=d.status,note=d.note[:240]);db.add(x);db.flush();db.add(Audit(actor_id=u.id,action="attendance.marked",details=f"{x.id}: student {d.student_id} {d.status}"));db.commit();return {"id":x.id,"status":x.status}
@app.post("/api/classes/{cid}/attendance/sessions")
def create_attendance_session(cid:int,u:User=Depends(roles("teacher","admin")),db:Session=Depends(dbdep)):
 c=access(db,u,cid)
 if u.role=="teacher" and c.teacher_id!=u.id:raise HTTPException(403,"Only the class teacher can start attendance")
 for active in db.scalars(select(AttendanceSession).where(AttendanceSession.class_id==cid,AttendanceSession.active==True)).all():active.active=False
 raw=secrets.token_urlsafe(24);expires=datetime.utcnow()+timedelta(minutes=8)
 session=AttendanceSession(class_id=cid,teacher_id=u.id,code_hash=hashlib.sha256(raw.encode()).hexdigest(),expires=expires,active=True)
 db.add(session);db.flush();db.add(Audit(actor_id=u.id,action="attendance.session_started",details=f"Class {cid}; session {session.id}; expires {expires.isoformat()}"));db.commit()
 return {"id":session.id,"code":raw,"expires":expires.isoformat()+"Z","minutes":8}
@app.post("/api/classes/{cid}/attendance/check-in")
def qr_check_in(cid:int,d:AttendanceCodeInput,u:User=Depends(roles("student")),db:Session=Depends(dbdep)):
 c=access(db,u,cid)
 session=db.scalar(select(AttendanceSession).where(AttendanceSession.class_id==cid,AttendanceSession.code_hash==hashlib.sha256(d.code.encode()).hexdigest(),AttendanceSession.active==True))
 if not session or session.expires<datetime.utcnow():raise HTTPException(400,"This attendance code has expired. Ask your teacher for a new one.")
 if not db.scalar(select(Enrollment.id).where(Enrollment.class_id==cid,Enrollment.student_id==u.id)):raise HTTPException(403,"Join this class before checking in")
 existing=db.scalar(select(Attendance).where(Attendance.session_id==session.id,Attendance.student_id==u.id))
 if existing:return {"id":existing.id,"status":existing.status,"message":"Your attendance is already recorded."}
 row=Attendance(class_id=cid,student_id=u.id,teacher_id=session.teacher_id,status="present",source="qr",session_id=session.id,note="QR check-in")
 db.add(row);db.flush();db.add(Audit(actor_id=u.id,action="attendance.qr_checkin",details=f"Attendance {row.id}; class {cid}"));db.add(Notification(user_id=session.teacher_id,title="QR attendance check-in",body=f"{u.name} checked in to {c.name}."));db.commit()
 return {"id":row.id,"status":row.status,"message":"Attendance recorded successfully."}
@app.put("/api/classes/{cid}/attendance/sessions/{sid}/close")
def close_attendance_session(cid:int,sid:int,u:User=Depends(roles("teacher","admin")),db:Session=Depends(dbdep)):
 c=access(db,u,cid)
 if u.role=="teacher" and c.teacher_id!=u.id:raise HTTPException(403,"Only the class teacher can close attendance")
 session=db.scalar(select(AttendanceSession).where(AttendanceSession.id==sid,AttendanceSession.class_id==cid))
 if not session:raise HTTPException(404,"Attendance session not found")
 session.active=False;db.add(Audit(actor_id=u.id,action="attendance.session_closed",details=f"Session {sid}; class {cid}"));db.commit();return {"ok":True}
@app.get("/api/classes/{cid}/attendance")
def attendance(cid:int,u:User=Depends(me),db:Session=Depends(dbdep)):
 c=access(db,u,cid)
 if u.role=="teacher" and c.teacher_id!=u.id:raise HTTPException(403,"Forbidden")
 q=select(Attendance,User).join(User,User.id==Attendance.student_id).where(Attendance.class_id==cid)
 if u.role=="student":q=q.where(Attendance.student_id==u.id)
 return [{"id":x.id,"student":st.name,"status":x.status,"source":x.source,"note":x.note,"created":x.created.isoformat()} for x,st in db.execute(q.order_by(Attendance.created.desc())).all()]
@app.delete("/api/classes/{cid}/attendance")
def clear_attendance(cid:int,u:User=Depends(roles("teacher","admin")),db:Session=Depends(dbdep)):
 c=access(db,u,cid)
 if u.role=="teacher" and c.teacher_id!=u.id:raise HTTPException(403,"Only the class teacher can clear attendance")
 sessions=db.scalars(select(AttendanceSession).where(AttendanceSession.class_id==cid,AttendanceSession.active==True)).all()
 for session in sessions:session.active=False
 records=db.scalars(select(Attendance).where(Attendance.class_id==cid)).all();count=len(records)
 for record in records:db.delete(record)
 db.add(Audit(actor_id=u.id,action="attendance.cleared",details=f"Class {cid}; deleted {count} records; closed {len(sessions)} active sessions"));db.commit()
 return {"ok":True,"deleted":count,"closed_sessions":len(sessions)}
@app.get("/api/classes/{cid}/attendance.csv")
def attendance_csv(cid:int,status:str|None=None,student_id:int|None=None,u:User=Depends(me),db:Session=Depends(dbdep)):
 c=access(db,u,cid)
 if u.role=="teacher" and c.teacher_id!=u.id:raise HTTPException(403,"Forbidden")
 if status and status not in ("present","late","absent","excused"):raise HTTPException(400,"Invalid status filter")
 if u.role=="student" and student_id not in (None,u.id):raise HTTPException(403,"Students may only export their own attendance")
 q=select(Attendance,User).join(User,User.id==Attendance.student_id).where(Attendance.class_id==cid)
 if status:q=q.where(Attendance.status==status)
 if student_id:q=q.where(Attendance.student_id==student_id)
 if u.role=="student":q=q.where(Attendance.student_id==u.id)
 output=io.StringIO();writer=csv.writer(output);writer.writerow(["Student","Student ID","Status","Note","Recorded at"])
 for item,student in db.execute(q.order_by(Attendance.created.desc())).all():writer.writerow([student.name,student.identifier,item.status,item.note,item.created.isoformat()])
 output.seek(0)
 return StreamingResponse(iter([output.getvalue()]),media_type="text/csv",headers={"Content-Disposition":f'attachment; filename="class-{cid}-attendance.csv"'})
@app.get("/api/classes/{cid}/attendance.xlsx")
def attendance_xlsx(cid:int,status:str|None=None,student_id:int|None=None,u:User=Depends(me),db:Session=Depends(dbdep)):
 c=access(db,u,cid)
 if u.role=="teacher" and c.teacher_id!=u.id:raise HTTPException(403,"Forbidden")
 if status and status not in ("present","late","absent","excused"):raise HTTPException(400,"Invalid status filter")
 if u.role=="student" and student_id not in (None,u.id):raise HTTPException(403,"Students may only export their own attendance")
 q=select(Attendance,User).join(User,User.id==Attendance.student_id).where(Attendance.class_id==cid)
 if status:q=q.where(Attendance.status==status)
 if student_id:q=q.where(Attendance.student_id==student_id)
 if u.role=="student":q=q.where(Attendance.student_id==u.id)
 from openpyxl import Workbook
 workbook=Workbook();sheet=workbook.active;sheet.title="Attendance";sheet.append(["Student","Student ID","Status","Note","Recorded at"])
 for item,student in db.execute(q.order_by(Attendance.created.desc())).all():sheet.append([student.name,student.identifier,item.status,item.note,item.created.isoformat()])
 buffer=io.BytesIO();workbook.save(buffer);buffer.seek(0)
 return StreamingResponse(buffer,media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":f'attachment; filename="class-{cid}-attendance.xlsx"'})
@app.get("/api/classes/{cid}/attendance.pdf")
def attendance_pdf(cid:int,status:str|None=None,student_id:int|None=None,u:User=Depends(me),db:Session=Depends(dbdep)):
 c=access(db,u,cid)
 if u.role=="teacher" and c.teacher_id!=u.id:raise HTTPException(403,"Forbidden")
 if status and status not in ("present","late","absent","excused"):raise HTTPException(400,"Invalid status filter")
 if u.role=="student" and student_id not in (None,u.id):raise HTTPException(403,"Students may only export their own attendance")
 q=select(Attendance,User).join(User,User.id==Attendance.student_id).where(Attendance.class_id==cid)
 if status:q=q.where(Attendance.status==status)
 if student_id:q=q.where(Attendance.student_id==student_id)
 if u.role=="student":q=q.where(Attendance.student_id==u.id)
 from reportlab.lib import colors
 from reportlab.lib.pagesizes import letter,landscape
 from reportlab.lib.styles import getSampleStyleSheet
 from reportlab.platypus import SimpleDocTemplate,Table,TableStyle,Paragraph,Spacer
 buffer=io.BytesIO();doc=SimpleDocTemplate(buffer,pagesize=landscape(letter));rows=[["Student","Student ID","Status","Note","Recorded at"]]
 rows.extend([[student.name,student.identifier,item.status,item.note,item.created.isoformat()] for item,student in db.execute(q.order_by(Attendance.created.desc())).all()])
 table=Table(rows,repeatRows=1);table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#294234")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.4,colors.HexColor("#ccd4cb")),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f3f6f2")]),("FONTSIZE",(0,0),(-1,-1),8),("PADDING",(0,0),(-1,-1),6)]))
 doc.build([Paragraph(c.name,getSampleStyleSheet()["Title"]),Spacer(1,12),table]);buffer.seek(0)
 return StreamingResponse(buffer,media_type="application/pdf",headers={"Content-Disposition":f'attachment; filename="class-{cid}-attendance.pdf"'})
@app.get("/api/notifications")
def notifications(u:User=Depends(me),db:Session=Depends(dbdep)):
 return [{"id":n.id,"title":n.title,"body":n.body,"read":n.read} for n in db.scalars(select(Notification).where(Notification.user_id==u.id).order_by(Notification.id.desc()).limit(50)).all()]
@app.put("/api/notifications/{nid}/read")
def read_notice(nid:int,u:User=Depends(me),db:Session=Depends(dbdep)):
 n=db.get(Notification,nid)
 if not n or n.user_id!=u.id:raise HTTPException(404,"Notification not found")
 n.read=True;db.commit();return {"ok":True}
@app.get("/api/admin/users")
def admin_users(u:User=Depends(roles("admin")),db:Session=Depends(dbdep)):
 return [ud(x)|{"approved":x.approved,"active":x.active,"email_verified":x.email_verified} for x in db.scalars(select(User).order_by(User.created.desc())).all()]
@app.put("/api/admin/users/{uid}/approve")
def approve(uid:int,u:User=Depends(roles("admin")),db:Session=Depends(dbdep)):
 x=db.get(User,uid)
 if not x or x.role!="teacher":raise HTTPException(404,"Teacher not found")
 x.approved=True;db.commit();return {"ok":True}
@app.put("/api/admin/users/{uid}/suspend")
def suspend_user(uid:int,u:User=Depends(roles("admin")),db:Session=Depends(dbdep)):
 target=db.get(User,uid)
 if not target or target.role not in ("student","teacher"):raise HTTPException(404,"Student or teacher account not found")
 target.active=False;target.session_version+=1;db.add(Audit(actor_id=u.id,action="user.suspended",details=f"user={uid}"));db.commit();return {"ok":True}
@app.put("/api/admin/users/{uid}/restore")
def restore_user(uid:int,u:User=Depends(roles("admin")),db:Session=Depends(dbdep)):
 target=db.get(User,uid)
 if not target or target.role not in ("student","teacher"):raise HTTPException(404,"Student or teacher account not found")
 target.active=True;target.session_version+=1;db.add(Audit(actor_id=u.id,action="user.restored",details=f"user={uid}"));db.commit();return {"ok":True}
@app.post("/api/admin/classes/{cid}/enroll/{student_id}")
def admin_enroll(cid:int,student_id:int,u:User=Depends(roles("admin")),db:Session=Depends(dbdep)):
 c=db.get(Classroom,cid);student=db.get(User,student_id)
 if not c:raise HTTPException(404,"Class not found")
 if not student or student.role!="student" or not student.active:raise HTTPException(404,"Active student not found")
 if not db.scalar(select(Enrollment.id).where(Enrollment.class_id==cid,Enrollment.student_id==student_id)):
  db.add(Enrollment(class_id=cid,student_id=student_id));db.add(Notification(user_id=student_id,title="Class enrollment",body=f"You were enrolled in {c.name}."));db.commit()
 return {"ok":True}
@app.get("/api/admin/audit")
def audit(u:User=Depends(roles("admin")),db:Session=Depends(dbdep)):
 return [{"actor":db.get(User,x.actor_id).name,"action":x.action,"details":x.details,"created":x.created.isoformat()} for x in db.scalars(select(Audit).order_by(Audit.created.desc()).limit(200)).all()]
@app.get("/api/classes/{cid}/announcements")
def list_announcements(cid:int,u:User=Depends(me),db:Session=Depends(dbdep)):
 access(db,u,cid)
 return [{"id":x.id,"title":x.title,"body":x.body,"priority":x.priority,"created":x.created.isoformat()} for x in db.scalars(select(Announcement).where(Announcement.class_id==cid).order_by(Announcement.created.desc())).all()]
@app.post("/api/classes/{cid}/announcements")
def create_announcement(cid:int,d:AnnouncementInput,u:User=Depends(me),db:Session=Depends(dbdep)):
 if u.role not in ("teacher","admin"):raise HTTPException(403,"Only teachers and admins can publish class announcements.")
 if u.role=="teacher" and not u.approved:raise HTTPException(403,"Teacher approval required before publishing announcements.")
 c=access(db,u,cid)
 if u.role=="teacher" and c.teacher_id!=u.id:raise HTTPException(403,"Only the class teacher can post")
 if d.priority not in ("normal","important","urgent"):raise HTTPException(400,"Invalid priority")
 x=Announcement(class_id=cid,teacher_id=u.id,title=d.title[:180],body=d.body[:10000],priority=d.priority);db.add(x);db.flush()
 for enrollment in c.enrollments:db.add(Notification(user_id=enrollment.student_id,title="Class announcement",body=x.title[:450]))
 db.commit();return {"id":x.id,"title":x.title}
@app.delete("/api/classes/{cid}/announcements/{aid}")
def delete_announcement(cid:int,aid:int,u:User=Depends(roles("teacher","admin")),db:Session=Depends(dbdep)):
 c=access(db,u,cid)
 if u.role=="teacher" and c.teacher_id!=u.id:raise HTTPException(403,"Only the class teacher can delete announcements")
 item=db.scalar(select(Announcement).where(Announcement.id==aid,Announcement.class_id==cid))
 if not item:raise HTTPException(404,"Announcement not found")
 db.delete(item);db.add(Audit(actor_id=u.id,action="announcement.deleted",details=f"Class {cid}; announcement {aid}"));db.commit();return {"ok":True}
@app.post("/api/classes/{cid}/materials")
async def upload_material(cid:int,file:UploadFile=File(...),u:User=Depends(roles("teacher","admin")),db:Session=Depends(dbdep)):
 c=access(db,u,cid)
 if u.role=="teacher" and c.teacher_id!=u.id:raise HTTPException(403,"Only the class teacher can upload")
 ext=Path(file.filename or "").suffix.lower()
 if ext not in ALLOWED_UPLOADS:raise HTTPException(415,"File type is not allowed")
 data=await file.read(upload_limit()+1)
 if len(data)>upload_limit():raise HTTPException(413,"File exceeds the upload limit")
 if not validate_upload(ext,data):raise HTTPException(415,"File content does not match the selected file type")
 stored=secrets.token_hex(20)+ext
 (UPLOADS/stored).write_bytes(data)
 item=Material(class_id=cid,uploader_id=u.id,name=Path(file.filename or "material").name[:240],stored_name=stored,size=len(data))
 db.add(item);db.commit();db.refresh(item)
 return {"id":item.id,"name":item.name,"size":item.size}
@app.get("/api/classes/{cid}/materials")
def list_materials(cid:int,u:User=Depends(me),db:Session=Depends(dbdep)):
 access(db,u,cid)
 return [{"id":m.id,"name":m.name,"size":m.size,"created":m.created.isoformat()} for m in db.scalars(select(Material).where(Material.class_id==cid).order_by(Material.created.desc())).all()]
@app.get("/api/classes/{cid}/materials/{mid}/download")
def download_material(cid:int,mid:int,u:User=Depends(me),db:Session=Depends(dbdep)):
 access(db,u,cid)
 item=db.scalar(select(Material).where(Material.id==mid,Material.class_id==cid))
 if not item:raise HTTPException(404,"Material not found")
 path=UPLOADS/item.stored_name
 if not path.is_file():raise HTTPException(404,"Material file not found")
 return FileResponse(path,filename=item.name)
@app.delete("/api/classes/{cid}/materials/{mid}")
def delete_material(cid:int,mid:int,u:User=Depends(roles("teacher","admin")),db:Session=Depends(dbdep)):
 c=access(db,u,cid)
 if u.role=="teacher" and c.teacher_id!=u.id:raise HTTPException(403,"Only the class teacher can delete materials")
 item=db.scalar(select(Material).where(Material.id==mid,Material.class_id==cid))
 if not item:raise HTTPException(404,"Material not found")
 path=UPLOADS/item.stored_name;name=item.name
 db.delete(item);db.add(Audit(actor_id=u.id,action="material.deleted",details=f"Class {cid}; {name}"));db.commit();path.unlink(missing_ok=True)
 return {"ok":True}
@app.get("/api/google/status")
def google_status(u:User=Depends(roles("teacher","admin")),db:Session=Depends(dbdep)):
 connected=db.scalar(select(GoogleCredential.id).where(GoogleCredential.user_id==u.id)) is not None
 return {"configured":google_configured(),"connected":connected}
@app.get("/api/google/connect")
def google_connect(req:Request,u:User=Depends(roles("teacher","admin"))):
 flow=google_flow()
 url,state=flow.authorization_url(access_type="offline",include_granted_scopes="true",prompt="consent")
 req.session["google_oauth_state"]=state
 return {"authorization_url":url}
@app.get("/api/google/callback")
def google_callback(req:Request,state:str,db:Session=Depends(dbdep)):
 expected=req.session.pop("google_oauth_state",None);user_id=req.session.get("uid")
 if not expected or not secrets.compare_digest(expected,state) or not user_id:raise HTTPException(400,"Google OAuth state is invalid or expired")
 user=db.get(User,user_id)
 if not user or user.role not in ("teacher","admin"):raise HTTPException(403,"Teacher or administrator account required")
 flow=google_flow(state=state)
 try:flow.fetch_token(authorization_response=str(req.url))
 except Exception:raise HTTPException(400,"Google authorization failed; try connecting again")
 saved=db.scalar(select(GoogleCredential).where(GoogleCredential.user_id==user.id))
 if not saved:saved=GoogleCredential(user_id=user.id,token_ciphertext="");db.add(saved)
 saved.token_ciphertext=token_cipher().encrypt(flow.credentials.to_json().encode()).decode();saved.updated=datetime.utcnow();db.commit()
 from fastapi.responses import RedirectResponse
 return RedirectResponse(os.getenv("FRONTEND_ORIGIN","http://localhost:5173")+"?google=connected")
@app.delete("/api/google/disconnect")
def google_disconnect(u:User=Depends(roles("teacher","admin")),db:Session=Depends(dbdep)):
 saved=db.scalar(select(GoogleCredential).where(GoogleCredential.user_id==u.id))
 if saved:db.delete(saved);db.commit()
 return {"ok":True}
def virtual_presence_json(db:Session,room:VirtualRoom,now:datetime|None=None):
 now=now or datetime.utcnow();stale_before=now-timedelta(seconds=45)
 for item in db.scalars(select(VirtualPresence).where(VirtualPresence.room_id==room.id,VirtualPresence.left_at.is_(None))).all():
  if not room.active or item.last_seen<stale_before:
   item.left_at=room.ended or item.last_seen;item.duration_seconds=max(0,int((item.left_at-item.joined_at).total_seconds()))
 db.flush()
 rows=db.execute(select(VirtualPresence,User).join(User,User.id==VirtualPresence.user_id).where(VirtualPresence.room_id==room.id,VirtualPresence.left_at.is_(None)).order_by(VirtualPresence.joined_at)).all()
 return [{"id":p.id,"user_id":person.id,"name":person.name,"role":person.role,"avatar_url":f"/api/users/{person.id}/avatar?v={person.avatar_name}" if person.avatar_name else None,"joined_at":p.joined_at.isoformat()+"Z"} for p,person in rows]
def virtual_room_json(db:Session,room:VirtualRoom):
 return {"id":room.id,"class_id":room.class_id,"title":room.title,"active":room.active,"created":room.created.isoformat()+"Z","ended":room.ended.isoformat()+"Z" if room.ended else None,"participants":len(virtual_presence_json(db,room)) if room.active else 0}
@app.get("/api/classes/{cid}/virtual-rooms")
def list_virtual_rooms(cid:int,u:User=Depends(me),db:Session=Depends(dbdep)):
 access(db,u,cid)
 rooms=db.scalars(select(VirtualRoom).where(VirtualRoom.class_id==cid,VirtualRoom.archived.is_(False)).order_by(VirtualRoom.created.desc()).limit(30)).all()
 result=[]
 for room in rooms:
  item=virtual_room_json(db,room);item["teacher"]=db.get(User,room.teacher_id).name;result.append(item)
 db.commit();return result
@app.delete("/api/classes/{cid}/virtual-rooms")
def clear_virtual_room_history(cid:int,u:User=Depends(roles("teacher","admin")),db:Session=Depends(dbdep)):
 c=access(db,u,cid)
 if u.role=="teacher" and c.teacher_id!=u.id:raise HTTPException(403,"Only the class teacher can clear virtual class history")
 rooms=db.scalars(select(VirtualRoom).where(VirtualRoom.class_id==cid,VirtualRoom.active.is_(False),VirtualRoom.archived.is_(False))).all()
 for room in rooms:room.archived=True
 db.commit();return {"cleared":len(rooms)}
@app.post("/api/classes/{cid}/virtual-rooms")
def create_virtual_room(cid:int,d:VirtualRoomInput,u:User=Depends(roles("teacher","admin")),db:Session=Depends(dbdep)):
 c=access(db,u,cid)
 if u.role=="teacher" and c.teacher_id!=u.id:raise HTTPException(403,"Only the class teacher can start a virtual class")
 now=datetime.utcnow()
 for old in db.scalars(select(VirtualRoom).where(VirtualRoom.class_id==cid,VirtualRoom.active==True)).all():
  old.active=False;old.ended=now;virtual_presence_json(db,old,now)
 room=VirtualRoom(class_id=cid,teacher_id=u.id,title=d.title.strip(),active=True,created=now);db.add(room);db.commit();db.refresh(room)
 return virtual_room_json(db,room)
@app.post("/api/virtual-rooms/{rid}/join")
def join_virtual_room(rid:int,u:User=Depends(me),db:Session=Depends(dbdep)):
 room=db.get(VirtualRoom,rid)
 if not room:raise HTTPException(404,"Virtual class not found")
 access(db,u,room.class_id)
 if not room.active:raise HTTPException(409,"This virtual class has ended")
 now=datetime.utcnow();virtual_presence_json(db,room,now)
 presence=VirtualPresence(room_id=rid,user_id=u.id,joined_at=now,last_seen=now);db.add(presence);db.commit();db.refresh(presence)
 return {"presence_id":presence.id,"room":virtual_room_json(db,room),"participants":virtual_presence_json(db,room,now)}
@app.get("/api/virtual-rooms/{rid}/state")
def virtual_room_state(rid:int,u:User=Depends(me),db:Session=Depends(dbdep)):
 room=db.get(VirtualRoom,rid)
 if not room:raise HTTPException(404,"Virtual class not found")
 access(db,u,room.class_id);participants=virtual_presence_json(db,room);db.commit()
 return {"room":virtual_room_json(db,room),"participants":participants}
@app.post("/api/virtual-rooms/{rid}/heartbeat")
def virtual_room_heartbeat(rid:int,d:VirtualPresenceInput,u:User=Depends(me),db:Session=Depends(dbdep)):
 room=db.get(VirtualRoom,rid);presence=db.get(VirtualPresence,d.presence_id)
 if not room or not presence or presence.room_id!=rid or presence.user_id!=u.id:raise HTTPException(404,"Virtual class presence was not found")
 if not room.active:
  if presence.left_at is None:presence.left_at=room.ended or datetime.utcnow();presence.duration_seconds=max(0,int((presence.left_at-presence.joined_at).total_seconds()));db.commit()
  return {"active":False}
 presence.last_seen=datetime.utcnow();db.commit();return {"active":True}
@app.post("/api/virtual-rooms/{rid}/leave")
def leave_virtual_room(rid:int,d:VirtualPresenceInput,u:User=Depends(me),db:Session=Depends(dbdep)):
 room=db.get(VirtualRoom,rid);presence=db.get(VirtualPresence,d.presence_id)
 if not room or not presence or presence.room_id!=rid or presence.user_id!=u.id:raise HTTPException(404,"Virtual class presence was not found")
 if presence.left_at is None:
  presence.last_seen=datetime.utcnow();presence.left_at=presence.last_seen;presence.duration_seconds=max(0,int((presence.left_at-presence.joined_at).total_seconds()));db.commit()
 return {"left_at":presence.left_at.isoformat()+"Z","duration_seconds":presence.duration_seconds}
@app.put("/api/virtual-rooms/{rid}/close")
def close_virtual_room(rid:int,u:User=Depends(roles("teacher","admin")),db:Session=Depends(dbdep)):
 room=db.get(VirtualRoom,rid)
 if not room:raise HTTPException(404,"Virtual class not found")
 c=access(db,u,room.class_id)
 if u.role=="teacher" and c.teacher_id!=u.id:raise HTTPException(403,"Only the class teacher can end this virtual class")
 room.active=False;room.ended=datetime.utcnow();virtual_presence_json(db,room,room.ended);db.commit();return {"ok":True}
@app.post("/api/virtual-rooms/{rid}/signals")
def send_virtual_signal(rid:int,d:VirtualSignalInput,u:User=Depends(me),db:Session=Depends(dbdep)):
 room=db.get(VirtualRoom,rid)
 if not room or not room.active:raise HTTPException(404,"Active virtual class not found")
 access(db,u,room.class_id);sender=db.get(VirtualPresence,d.sender_presence_id);recipient=db.get(VirtualPresence,d.recipient_presence_id)
 if not sender or sender.room_id!=rid or sender.user_id!=u.id or sender.left_at is not None:raise HTTPException(403,"Join the virtual class before sending signals")
 if not recipient or recipient.room_id!=rid or recipient.left_at is not None:raise HTTPException(404,"Class participant is no longer connected")
 if d.payload.get("kind")=="command":
  if u.role not in ("teacher","admin") or (u.role=="teacher" and room.teacher_id!=u.id):raise HTTPException(403,"Only the meeting host can moderate participants")
  if d.payload.get("command") not in ("mute-audio","stop-video","remove"):raise HTTPException(400,"Unknown meeting moderation command")
 payload=json.dumps(d.payload,separators=(",",":"))
 if len(payload)>100000:raise HTTPException(413,"Call setup message is too large")
 signal=VirtualSignal(room_id=rid,sender_presence_id=sender.id,recipient_presence_id=recipient.id,payload=payload);db.add(signal);db.commit();return {"id":signal.id}
@app.get("/api/virtual-rooms/{rid}/signals")
def receive_virtual_signals(rid:int,presence_id:int,after:int=0,u:User=Depends(me),db:Session=Depends(dbdep)):
 room=db.get(VirtualRoom,rid);presence=db.get(VirtualPresence,presence_id)
 if not room or not presence or presence.room_id!=rid or presence.user_id!=u.id:raise HTTPException(404,"Virtual class presence was not found")
 access(db,u,room.class_id)
 rows=db.execute(select(VirtualSignal,VirtualPresence,User).join(VirtualPresence,VirtualPresence.id==VirtualSignal.sender_presence_id).join(User,User.id==VirtualPresence.user_id).where(VirtualSignal.room_id==rid,VirtualSignal.recipient_presence_id==presence_id,VirtualSignal.id>after).order_by(VirtualSignal.id).limit(100)).all()
 return [{"id":signal.id,"from_presence_id":signal.sender_presence_id,"from_name":person.name,"from_role":person.role,"payload":json.loads(signal.payload)} for signal,_,person in rows]
@app.get("/api/classes/{cid}/virtual-attendance")
def virtual_attendance(cid:int,u:User=Depends(roles("teacher","admin")),db:Session=Depends(dbdep)):
 c=access(db,u,cid)
 if u.role=="teacher" and c.teacher_id!=u.id:raise HTTPException(403,"Only the class teacher can review virtual attendance")
 rooms=db.scalars(select(VirtualRoom).where(VirtualRoom.class_id==cid).order_by(VirtualRoom.created.desc())).all();out=[]
 for room in rooms:
  virtual_presence_json(db,room)
  entries=db.execute(select(VirtualPresence,User).join(User,User.id==VirtualPresence.user_id).where(VirtualPresence.room_id==room.id).order_by(VirtualPresence.joined_at)).all()
  for p,person in entries:out.append({"room_id":room.id,"title":room.title,"student":person.name,"role":person.role,"joined_at":p.joined_at.isoformat()+"Z","left_at":p.left_at.isoformat()+"Z" if p.left_at else None,"duration_seconds":p.duration_seconds,"active":p.left_at is None and room.active})
 db.commit();return out
@app.delete("/api/classes/{cid}/virtual-attendance")
def clear_virtual_attendance(cid:int,u:User=Depends(roles("teacher","admin")),db:Session=Depends(dbdep)):
 c=access(db,u,cid)
 if u.role=="teacher" and c.teacher_id!=u.id:raise HTTPException(403,"Only the class teacher can clear virtual attendance")
 rooms=db.scalars(select(VirtualRoom).where(VirtualRoom.class_id==cid)).all()
 for room in rooms:virtual_presence_json(db,room)
 presence_ids=list(db.scalars(select(VirtualPresence.id).join(VirtualRoom,VirtualRoom.id==VirtualPresence.room_id).where(VirtualRoom.class_id==cid,VirtualPresence.left_at.is_not(None))))
 if presence_ids:
  db.execute(delete(VirtualSignal).where((VirtualSignal.sender_presence_id.in_(presence_ids))|(VirtualSignal.recipient_presence_id.in_(presence_ids))))
  result=db.execute(delete(VirtualPresence).where(VirtualPresence.id.in_(presence_ids)))
  db.commit();return {"ok":True,"cleared":result.rowcount or 0}
 return {"ok":True,"cleared":0}
@app.post("/api/classes/{cid}/meetings")
def create_meeting(cid:int,d:MeetingInput,u:User=Depends(roles("teacher","admin")),db:Session=Depends(dbdep)):
 c=access(db,u,cid)
 if u.role=="teacher" and c.teacher_id!=u.id:raise HTTPException(403,"Only the class teacher can schedule meetings")
 if d.ends<=d.starts:raise HTTPException(400,"Meeting end must be after its start")
 creds=google_credentials(u,db)
 from google.auth.transport.requests import AuthorizedSession
 start=d.starts if d.starts.tzinfo else d.starts.replace(tzinfo=timezone.utc)
 end=d.ends if d.ends.tzinfo else d.ends.replace(tzinfo=timezone.utc)
 event={"summary":d.title[:180],"description":c.name+" · Classflow virtual classroom","start":{"dateTime":start.astimezone(timezone.utc).isoformat().replace("+00:00","Z")},"end":{"dateTime":end.astimezone(timezone.utc).isoformat().replace("+00:00","Z")},"attendees":[{"email":student.email} for enrollment in c.enrollments if (student:=db.get(User,enrollment.student_id)) and student.email],"conferenceData":{"createRequest":{"requestId":secrets.token_hex(12),"conferenceSolutionKey":{"type":"hangoutsMeet"}}}}
 try:
  response=AuthorizedSession(creds).post("https://www.googleapis.com/calendar/v3/calendars/primary/events",params={"conferenceDataVersion":1,"sendUpdates":"all"},json=event,timeout=25)
 except requests.RequestException:raise HTTPException(502,"Could not reach Google Calendar")
 if response.status_code>=400:raise HTTPException(502,"Google Calendar rejected meeting creation; check Calendar API and OAuth scopes")
 result=response.json();meet_url=result.get("hangoutLink","")
 if not meet_url:raise HTTPException(502,"Google has not generated a Meet link yet; retry or add a link manually")
 match=re.search(r"meet\.google\.com/([a-z]{3}-[a-z]{4}-[a-z]{3})",meet_url.lower())
 code=match.group(1) if match else ""
 meeting=Meeting(class_id=cid,creator_id=u.id,title=d.title[:180],starts=start.astimezone(timezone.utc).replace(tzinfo=None),ends=end.astimezone(timezone.utc).replace(tzinfo=None),meet_url=meet_url,meeting_code=code,calendar_event_id=result["id"])
 db.add(meeting);c.meet=meet_url;db.commit();db.refresh(meeting)
 return {"id":meeting.id,"title":meeting.title,"meet_url":meeting.meet_url,"starts":meeting.starts.isoformat()+"Z","ends":meeting.ends.isoformat()+"Z"}
@app.get("/api/classes/{cid}/meetings")
def list_meetings(cid:int,u:User=Depends(me),db:Session=Depends(dbdep)):
 access(db,u,cid)
 return [{"id":m.id,"title":m.title,"meet_url":m.meet_url,"starts":m.starts.isoformat()+"Z","ends":m.ends.isoformat()+"Z"} for m in db.scalars(select(Meeting).where(Meeting.class_id==cid).order_by(Meeting.starts.desc())).all()]
@app.post("/api/classes/{cid}/meetings/{mid}/sync-attendance")
def sync_meet_attendance(cid:int,mid:int,u:User=Depends(roles("teacher","admin")),db:Session=Depends(dbdep)):
 c=access(db,u,cid)
 if u.role=="teacher" and c.teacher_id!=u.id:raise HTTPException(403,"Forbidden")
 meeting=db.scalar(select(Meeting).where(Meeting.id==mid,Meeting.class_id==cid))
 if not meeting:raise HTTPException(404,"Meeting not found")
 if not meeting.meeting_code:raise HTTPException(409,"No Meet code is available for this meeting")
 creds=google_credentials(u,db)
 lower=(meeting.starts-timedelta(hours=12)).replace(tzinfo=timezone.utc).isoformat().replace("+00:00","Z")
 upper=(meeting.ends+timedelta(hours=12)).replace(tzinfo=timezone.utc).isoformat().replace("+00:00","Z")
 filter_value=f'space.meeting_code = "{meeting.meeting_code}" AND start_time >= "{lower}" AND start_time <= "{upper}"'
 records=google_get(creds,"https://meet.googleapis.com/v2/conferenceRecords",{"filter":filter_value,"pageSize":100}).get("conferenceRecords",[])
 seen=0
 for conference in records:
  parent=conference["name"];page=None
  while True:
   params={"pageSize":250}
   if page:params["pageToken"]=page
   participants=google_get(creds,"https://meet.googleapis.com/v2/"+parent+"/participants",params)
   for p in participants.get("participants",[]):
    user_data=p.get("signedinUser") or p.get("anonymousUser") or p.get("phoneUser") or {}
    display=str(user_data.get("displayName") or "Unknown participant")[:200]
    session_page=None;times=[]
    while True:
     session_params={"pageSize":250}
     if session_page:session_params["pageToken"]=session_page
     session_data=google_get(creds,"https://meet.googleapis.com/v2/"+p["name"]+"/participantSessions",session_params)
     times.extend(session_data.get("participantSessions",[]));session_page=session_data.get("nextPageToken")
     if not session_page:break
    starts=[parse_google_time(t.get("startTime")) for t in times if t.get("startTime")]
    ends=[parse_google_time(t.get("endTime")) for t in times if t.get("endTime")]
    duration=sum(max(0,int((parse_google_time(t["endTime"])-parse_google_time(t["startTime"])).total_seconds())) for t in times if t.get("startTime") and t.get("endTime"))
    reference=conference["name"]+"/"+p["name"]
    item=db.scalar(select(MeetingParticipant).where(MeetingParticipant.meeting_id==mid,MeetingParticipant.participant_ref==reference))
    if not item:item=MeetingParticipant(meeting_id=mid,participant_ref=reference,display_name=display);db.add(item)
    item.display_name=display;item.joined_at=min(starts) if starts else None;item.left_at=max(ends) if ends else None;item.duration_seconds=duration;seen+=1
   page=participants.get("nextPageToken")
   if not page:break
 db.commit()
 return {"imported_participants":seen,"records_found":len(records),"requires_teacher_match":True}
@app.get("/api/classes/{cid}/meetings/{mid}/participants")
def meeting_participants(cid:int,mid:int,u:User=Depends(roles("teacher","admin")),db:Session=Depends(dbdep)):
 c=access(db,u,cid)
 if u.role=="teacher" and c.teacher_id!=u.id:raise HTTPException(403,"Forbidden")
 if not db.scalar(select(Meeting.id).where(Meeting.id==mid,Meeting.class_id==cid)):raise HTTPException(404,"Meeting not found")
 return [{"id":p.id,"display_name":p.display_name,"student_id":p.student_id,"confirmed":p.confirmed,"joined_at":p.joined_at.isoformat()+"Z" if p.joined_at else None,"left_at":p.left_at.isoformat()+"Z" if p.left_at else None,"duration_seconds":p.duration_seconds} for p in db.scalars(select(MeetingParticipant).where(MeetingParticipant.meeting_id==mid)).all()]
@app.put("/api/classes/{cid}/meetings/{mid}/participants/{pid}/confirm")
def confirm_meet_participant(cid:int,mid:int,pid:int,d:ConfirmParticipantInput,u:User=Depends(roles("teacher","admin")),db:Session=Depends(dbdep)):
 c=access(db,u,cid)
 if u.role=="teacher" and c.teacher_id!=u.id:raise HTTPException(403,"Forbidden")
 item=db.scalar(select(MeetingParticipant).where(MeetingParticipant.id==pid,MeetingParticipant.meeting_id==mid))
 student=db.get(User,d.student_id)
 if not item or not student:raise HTTPException(404,"Participant or student not found")
 if not db.scalar(select(Enrollment.id).where(Enrollment.class_id==cid,Enrollment.student_id==student.id)):raise HTTPException(400,"Student is not enrolled in this class")
 item.student_id=student.id;item.confirmed=True
 row=db.scalar(select(Attendance).where(Attendance.meeting_id==mid,Attendance.student_id==student.id))
 if not row:row=Attendance(class_id=cid,student_id=student.id,teacher_id=u.id,status="present",note="Teacher-confirmed Meet participant",source="meet_api",meeting_id=mid);db.add(row)
 late_after=meeting.starts+timedelta(minutes=10) if (meeting:=db.get(Meeting,mid)) else None
 row.status="late" if item.joined_at and late_after and item.joined_at>late_after else "present";row.note="Teacher confirmed Google Meet participant: "+item.display_name[:180];row.joined_at=item.joined_at;row.left_at=item.left_at;row.duration_seconds=item.duration_seconds;row.source="meet_api"
 db.add(Audit(actor_id=u.id,action="attendance.meet_confirmed",details=f"meeting={mid}; participant={pid}; student={student.id}"));db.commit()
 return {"ok":True,"attendance_id":row.id,"status":row.status}

frontend_dist=Path(os.getenv("FRONTEND_DIST",str(Path(__file__).resolve().parents[1]/"frontend-dist")))
if frontend_dist.is_dir():app.mount("/",StaticFiles(directory=str(frontend_dist),html=True),name="frontend")
