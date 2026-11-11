def register(client,name,email,role="student"):
    return client.post("/api/auth/register",json={"name":name,"email":email,"password":"CorrectHorseBattery!9","role":role})
def login(client,email):
    return client.post("/api/auth/login",json={"email":email,"password":"CorrectHorseBattery!9"})
def make_admin(client):
    response=register(client,"Admin User","admin@classflow.example.com")
    assert response.status_code==200,response.text
def make_teacher_and_class(client,name="Biology"):
    response=register(client,"Teacher One","teacher@classflow.example.com","teacher")
    tid=response.json()["id"]
    login(client,"admin@classflow.example.com")
    assert client.put(f"/api/admin/users/{tid}/approve").status_code==200
    login(client,"teacher@classflow.example.com")
    response=client.post("/api/classes",json={"name":name,"subject":name})
    assert response.status_code==200,response.text
    return response.json()
def test_teacher_approval_and_class_creation(client):
    make_admin(client)
    register(client,"Teacher One","teacher@classflow.example.com","teacher")
    assert client.post("/api/classes",json={"name":"Biology","subject":"Science"}).status_code==403
    login(client,"admin@classflow.example.com")
    tid=next(u["id"] for u in client.get("/api/admin/users").json() if u["email"]=="teacher@classflow.example.com")
    assert client.put(f"/api/admin/users/{tid}/approve").status_code==200
    login(client,"teacher@classflow.example.com")
    assert client.post("/api/classes",json={"name":"Biology","subject":"Science"}).status_code==200
def test_class_delete_is_owner_only_and_cleans_related_records(client):
    make_admin(client)
    course=make_teacher_and_class(client,"Biology")
    assignment=client.post(f"/api/classes/{course['id']}/assignments",json={"title":"Practice","instructions":"Read chapter 1"}).json()
    quiz=client.post(f"/api/classes/{course['id']}/quizzes",json={"title":"Review","duration":10,"questions":[{"prompt":"Question?","choices":["A","B"],"answer":1}]}).json()
    announcement=client.post(f"/api/classes/{course['id']}/announcements",json={"title":"Welcome","body":"Class starts Monday"}).json()
    material=client.post(f"/api/classes/{course['id']}/materials",files={"file":("notes.pdf",b"%PDF-1.4 test","application/pdf")}).json()
    from app.main import Announcement, Assignment, Attempt, DB, Enrollment, Material, Quiz, UPLOADS
    from sqlalchemy import select
    with DB() as db:
        material_path=UPLOADS/db.get(Material,material["id"]).stored_name
    register(client,"Student One","student@classflow.example.com")
    assert client.post(f"/api/classes/{course['id']}/join").status_code==200
    assert client.delete(f"/api/classes/{course['id']}").status_code==403
    login(client,"teacher@classflow.example.com")
    response=client.delete(f"/api/classes/{course['id']}")
    assert response.status_code==200,response.text
    assert client.delete(f"/api/classes/{course['id']}").status_code==404
    assert not material_path.exists()
    with DB() as db:
        assert db.get(Assignment,assignment["id"]) is None
        assert db.get(Quiz,quiz["id"]) is None
        assert db.get(Announcement,announcement["id"]) is None
        assert db.get(Material,material["id"]) is None
        assert db.scalar(select(Enrollment.id).where(Enrollment.class_id==course["id"])) is None
        assert db.scalar(select(Attempt.id).where(Attempt.quiz_id==quiz["id"])) is None
def test_open_class_directory_join_and_teacher_enrollment_control(client):
    make_admin(client)
    course=make_teacher_and_class(client,"Biology")
    assert course["enrollment_open"] is True
    register(client,"Student One","student@classflow.example.com")
    available=client.get("/api/classes/available")
    assert available.status_code==200
    assert [item["id"] for item in available.json()]==[course["id"]]
    instructor=available.json()[0]["instructor"]
    assert instructor["name"]=="Teacher One"
    assert instructor["role"]=="teacher"
    assert instructor["avatar_url"] is None
    assert client.post(f"/api/classes/{course['id']}/join").status_code==200
    assert client.get("/api/classes/available").json()==[]
    enrolled=next(item for item in client.get("/api/dashboard").json()["classes"] if item["id"]==course["id"])
    assert enrolled["instructor"]["name"]=="Teacher One"
    login(client,"teacher@classflow.example.com")
    assert client.put(f"/api/classes/{course['id']}/enrollment",json={"open":False}).json()=={"open":False}
    login(client,"student@classflow.example.com")
    assert client.post(f"/api/classes/join/{course['code']}").status_code==409
    assert client.get("/api/classes/available").json()==[]
def test_assignment_submission_is_class_scoped(client):
    make_admin(client)
    course=make_teacher_and_class(client,"Math")
    assignment=client.post(f"/api/classes/{course['id']}/assignments",json={"title":"Practice","instructions":"Solve","points":10}).json()
    register(client,"Student One","student1@classflow.example.com")
    assert client.post(f"/api/classes/join/{course['code']}").status_code==200
    assert client.post(f"/api/assignments/{assignment['id']}/submit",json={"answer":"Done"}).status_code==200
    register(client,"Student Two","student2@classflow.example.com")
    assert client.get(f"/api/classes/{course['id']}/assignments").status_code==403
def test_quiz_answer_hidden_and_submission_scored(client):
    make_admin(client)
    course=make_teacher_and_class(client,"Science")
    quiz=client.post(f"/api/classes/{course['id']}/quizzes",json={"title":"Quick check","duration":5,"questions":[{"prompt":"2 + 2?","choices":["3","4"],"answer":1}]})
    assert quiz.status_code==200,quiz.text
    register(client,"Student One","student@classflow.example.com")
    client.post(f"/api/classes/join/{course['code']}")
    public_quiz=client.get(f"/api/classes/{course['id']}/quizzes").json()[0]
    assert "answer" not in public_quiz["questions"][0]
    attempt=client.post(f"/api/quizzes/{quiz.json()['id']}/attempt",json={"answers":["1"],"submit":True})
    assert attempt.status_code==200,attempt.text
    assert attempt.json()["score"]==1
def test_attendance_requires_enrollment_and_is_recorded(client):
    make_admin(client)
    course=make_teacher_and_class(client,"History")
    login(client,"admin@classflow.example.com")
    register(client,"Student One","student@classflow.example.com")
    sid=client.get("/api/auth/me").json()["id"]
    client.post(f"/api/classes/join/{course['code']}")
    login(client,"teacher@classflow.example.com")
    result=client.post(f"/api/classes/{course['id']}/attendance",json={"student_id":sid,"status":"present"})
    assert result.status_code==200,result.text
    assert client.get(f"/api/classes/{course['id']}/attendance").json()[0]["status"]=="present"
    assert "text/csv" in client.get(f"/api/classes/{course['id']}/attendance.csv").headers["content-type"]
    assert "spreadsheetml" in client.get(f"/api/classes/{course['id']}/attendance.xlsx").headers["content-type"]
    assert client.get(f"/api/classes/{course['id']}/attendance.pdf").content.startswith(b"%PDF")
    session=client.post(f"/api/classes/{course['id']}/attendance/sessions").json()
    login(client,"student@classflow.example.com")
    assert client.post(f"/api/classes/{course['id']}/attendance/check-in",json={"code":session["code"]}).status_code==200
    login(client,"teacher@classflow.example.com")
    cleared=client.delete(f"/api/classes/{course['id']}/attendance")
    assert cleared.status_code==200 and cleared.json()["deleted"]==2 and cleared.json()["closed_sessions"]==1
    assert client.get(f"/api/classes/{course['id']}/attendance").json()==[]
    login(client,"student@classflow.example.com")
    assert client.post(f"/api/classes/{course['id']}/attendance/check-in",json={"code":session["code"]}).status_code==400

def test_announcements_and_materials_are_class_scoped(client):
    make_admin(client)
    course=make_teacher_and_class(client,"Literature")
    posted=client.post(f"/api/classes/{course['id']}/announcements",json={"title":"Read chapter 2","body":"Before Friday","priority":"important"})
    assert posted.status_code==200,posted.text
    uploaded=client.post(f"/api/classes/{course['id']}/materials",files={"file":("reading.pdf",b"%PDF-1.4 test", "application/pdf")})
    assert uploaded.status_code==200,uploaded.text
    material_id=uploaded.json()["id"]
    register(client,"Student One","student@classflow.example.com")
    denied=client.post(f"/api/classes/{course['id']}/announcements",json={"title":"Unauthorized","body":"Should not publish"})
    assert denied.status_code==403
    assert denied.json()["detail"]=="Only teachers and admins can publish class announcements."
    assert client.post(f"/api/classes/join/{course['code']}").status_code==200
    assert client.get(f"/api/classes/{course['id']}/announcements").json()[0]["title"]=="Read chapter 2"
    assert client.get(f"/api/classes/{course['id']}/materials/{material_id}/download").content.startswith(b"%PDF")
    from app.main import DB, Material, UPLOADS
    with DB() as db:
        stored=db.get(Material,material_id).stored_name
    assert client.delete(f"/api/classes/{course['id']}/announcements/{posted.json()['id']}").status_code==403
    assert client.delete(f"/api/classes/{course['id']}/materials/{material_id}").status_code==403
    login(client,"teacher@classflow.example.com")
    assert client.delete(f"/api/classes/{course['id']}/announcements/{posted.json()['id']}").status_code==200
    assert client.get(f"/api/classes/{course['id']}/announcements").json()==[]
    assert client.delete(f"/api/classes/{course['id']}/materials/{material_id}").status_code==200
    assert client.get(f"/api/classes/{course['id']}/materials/{material_id}/download").status_code==404
    assert not (UPLOADS/stored).exists()

def test_native_virtual_class_records_each_join_and_leave(client):
    make_admin(client)
    course=make_teacher_and_class(client,"Media Studies")
    register(client,"Student One","student@classflow.example.com")
    assert client.post(f"/api/classes/join/{course['code']}").status_code==200
    login(client,"teacher@classflow.example.com")
    started=client.post(f"/api/classes/{course['id']}/virtual-rooms",json={"title":"Live lesson"})
    assert started.status_code==200,started.text
    room=started.json()
    teacher_join=client.post(f"/api/virtual-rooms/{room['id']}/join")
    assert teacher_join.status_code==200,teacher_join.text
    teacher_presence=teacher_join.json()["presence_id"]
    login(client,"student@classflow.example.com")
    student_join=client.post(f"/api/virtual-rooms/{room['id']}/join")
    assert student_join.status_code==200,student_join.text
    student_presence=student_join.json()["presence_id"]
    assert len(student_join.json()["participants"])==2
    login(client,"teacher@classflow.example.com")
    sent=client.post(f"/api/virtual-rooms/{room['id']}/signals",json={"sender_presence_id":teacher_presence,"recipient_presence_id":student_presence,"payload":{"description":{"type":"offer","sdp":"test-session-description"}}})
    assert sent.status_code==200,sent.text
    login(client,"student@classflow.example.com")
    received=client.get(f"/api/virtual-rooms/{room['id']}/signals",params={"presence_id":student_presence,"after":0})
    assert received.status_code==200 and received.json()[0]["payload"]["description"]["type"]=="offer"
    assert client.post(f"/api/virtual-rooms/{room['id']}/heartbeat",json={"presence_id":student_presence}).json()["active"] is True
    assert client.post(f"/api/virtual-rooms/{room['id']}/leave",json={"presence_id":student_presence}).status_code==200
    login(client,"teacher@classflow.example.com")
    attendance=client.get(f"/api/classes/{course['id']}/virtual-attendance")
    assert attendance.status_code==200
    student_rows=[row for row in attendance.json() if row["student"]=="Student One"]
    assert len(student_rows)==1 and student_rows[0]["left_at"] is not None
    assert client.put(f"/api/virtual-rooms/{room['id']}/close").status_code==200
    assert client.get(f"/api/virtual-rooms/{room['id']}/state").json()["room"]["active"] is False

def test_clear_virtual_room_history_keeps_live_rooms_and_attendance(client):
    make_admin(client)
    course=make_teacher_and_class(client,"Media Studies")
    ended=client.post(f"/api/classes/{course['id']}/virtual-rooms",json={"title":"Ended lesson"}).json()
    teacher_join=client.post(f"/api/virtual-rooms/{ended['id']}/join").json()
    register(client,"Student One","student@classflow.example.com")
    assert client.post(f"/api/classes/join/{course['code']}").status_code==200
    student_join=client.post(f"/api/virtual-rooms/{ended['id']}/join")
    assert student_join.status_code==200,student_join.text
    login(client,"teacher@classflow.example.com")
    assert client.put(f"/api/virtual-rooms/{ended['id']}/close").status_code==200
    attendance_before=client.get(f"/api/classes/{course['id']}/virtual-attendance").json()
    live=client.post(f"/api/classes/{course['id']}/virtual-rooms",json={"title":"Current lesson"}).json()

    login(client,"student@classflow.example.com")
    assert client.delete(f"/api/classes/{course['id']}/virtual-rooms").status_code==403
    login(client,"teacher@classflow.example.com")
    cleared=client.delete(f"/api/classes/{course['id']}/virtual-rooms")

    assert cleared.status_code==200 and cleared.json()=={"cleared":1}
    assert [room["id"] for room in client.get(f"/api/classes/{course['id']}/virtual-rooms").json()]==[live["id"]]
    assert client.get(f"/api/virtual-rooms/{ended['id']}/state").json()["room"]["active"] is False
    assert client.get(f"/api/classes/{course['id']}/virtual-attendance").json()==attendance_before
    assert teacher_join["presence_id"]

def test_meet_api_import_requires_teacher_identity_confirmation(client,monkeypatch):
    make_admin(client)
    course=make_teacher_and_class(client,"Civics")
    register(client,"Student One","student@classflow.example.com")
    student_id=client.get("/api/auth/me").json()["id"]
    client.post(f"/api/classes/join/{course['code']}")
    login(client,"teacher@classflow.example.com")
    from datetime import datetime
    from app import main
    with main.DB() as db:
        meeting=main.Meeting(class_id=course["id"],creator_id=client.get("/api/auth/me").json()["id"],title="Civics",starts=datetime(2026,1,1),ends=datetime(2026,1,1,1),meet_url="https://meet.google.com/abc-defg-hij",meeting_code="abc-defg-hij",calendar_event_id="event1")
        db.add(meeting);db.commit();db.refresh(meeting);meeting_id=meeting.id
    monkeypatch.setattr(main,"google_configured",lambda:True)
    monkeypatch.setattr(main,"google_credentials",lambda user,db:object())
    def google_get(_credentials,url,params=None):
        if url.endswith("conferenceRecords"):
            return {"conferenceRecords":[{"name":"conferenceRecords/record1"}]}
        if url.endswith("/participants"):
            return {"participants":[{"name":"conferenceRecords/record1/participants/p1","signedinUser":{"displayName":"Student One"}}]}
        return {"participantSessions":[{"startTime":"2026-01-01T00:02:00Z","endTime":"2026-01-01T00:32:00Z"}]}
    monkeypatch.setattr(main,"google_get",google_get)
    synced=client.post(f"/api/classes/{course['id']}/meetings/{meeting_id}/sync-attendance")
    assert synced.status_code==200,synced.text
    participant=client.get(f"/api/classes/{course['id']}/meetings/{meeting_id}/participants").json()[0]
    assert participant["confirmed"] is False
    confirmed=client.put(f"/api/classes/{course['id']}/meetings/{meeting_id}/participants/{participant['id']}/confirm",json={"student_id":student_id})
    assert confirmed.status_code==200,confirmed.text
    assert client.get(f"/api/classes/{course['id']}/attendance").json()[0]["status"]=="present"

def test_assignment_file_submission_is_private(client):
    make_admin(client)
    course=make_teacher_and_class(client,"Writing")
    assignment=client.post(f"/api/classes/{course['id']}/assignments",json={"title":"Essay","instructions":"Upload a text response"}).json()
    register(client,"Student One","student1@classflow.example.com")
    client.post(f"/api/classes/join/{course['code']}")
    uploaded=client.post(f"/api/assignments/{assignment['id']}/upload",files={"file":("answer.txt",b"My answer", "text/plain")})
    assert uploaded.status_code==200,uploaded.text
    submission_id=uploaded.json()["id"]
    assert client.get(f"/api/submissions/{submission_id}/download").content==b"My answer"
    register(client,"Student Two","student2@classflow.example.com")
    assert client.get(f"/api/submissions/{submission_id}/download").status_code==404
    login(client,"teacher@classflow.example.com")
    detail=client.get(f"/api/classes/{course['id']}/assignments").json()[0]
    assert detail["submissions"][0]["file_name"]=="answer.txt"
    from app.main import DB, Submission, UPLOADS
    with DB() as db:
        stored=db.get(Submission,submission_id).stored_file
    (UPLOADS/stored).unlink(missing_ok=True)

def test_email_verification_and_password_reset_revoke_old_session(client,monkeypatch):
    import app.main as main
    monkeypatch.setenv("EMAIL_VERIFICATION_REQUIRED","true")
    sent=[]
    monkeypatch.setattr(main,"smtp_configured",lambda:True)
    monkeypatch.setattr(main,"send_email",lambda recipient,subject,body:sent.append(body))
    result=register(client,"Student One","verified@classflow.example.com")
    assert result.status_code==200 and result.json()["requires_verification"]
    assert client.post("/api/auth/login",json={"email":"verified@classflow.example.com","password":"CorrectHorseBattery!9"}).status_code==403
    verify_token=sent[-1].split("verify_token=")[1].split()[0]
    assert client.post("/api/auth/verify-email",json={"token":verify_token}).status_code==200
    assert login(client,"verified@classflow.example.com").status_code==200
    sent.clear()
    assert client.post("/api/auth/forgot-password",json={"email":"verified@classflow.example.com"}).status_code==200
    reset_token=sent[-1].split("reset_token=")[1].split()[0]
    assert client.post("/api/auth/reset-password",json={"token":reset_token,"password":"EvenStrongerPassword!5"}).status_code==200
    assert client.get("/api/auth/me").status_code==401
    assert client.post("/api/auth/login",json={"email":"verified@classflow.example.com","password":"CorrectHorseBattery!9"}).status_code==401
    assert client.post("/api/auth/login",json={"email":"verified@classflow.example.com","password":"EvenStrongerPassword!5"}).status_code==200

def test_admin_suspension_revokes_sessions_and_can_restore(client):
    make_admin(client)
    register(client,"Student One","student@classflow.example.com")
    student_id=client.get("/api/auth/me").json()["id"]
    login(client,"admin@classflow.example.com")
    assert client.put(f"/api/admin/users/{student_id}/suspend").status_code==200
    assert login(client,"student@classflow.example.com").status_code==403
    assert client.put(f"/api/admin/users/{student_id}/restore").status_code==200
    assert login(client,"student@classflow.example.com").status_code==200

def test_activity_submission_is_separate_from_assignments(client):
    make_admin(client)
    course=make_teacher_and_class(client,"Art")
    activity=client.post(f"/api/classes/{course['id']}/activities",json={"title":"Sketch study","instructions":"Submit a short reflection","points":10})
    assert activity.status_code==200,activity.text
    assert client.get(f"/api/classes/{course['id']}/activities").json()[0]["title"]=="Sketch study"
    assert client.get(f"/api/classes/{course['id']}/assignments").json()==[]
    register(client,"Student One","student@classflow.example.com")
    client.post(f"/api/classes/join/{course['code']}")
    submitted=client.post(f"/api/activities/{activity.json()['id']}/submit",json={"answer":"I used warm colors."})
    assert submitted.status_code==200,submitted.text
    assert client.get(f"/api/classes/{course['id']}/activities").json()[0]["submission"]["answer"]=="I used warm colors."

def test_private_class_messages_are_limited_to_teacher_and_enrolled_student(client):
    make_admin(client)
    course=make_teacher_and_class(client,"Physics")
    register(client,"Student One","student1@classflow.example.com")
    student_id=client.get("/api/auth/me").json()["id"]
    client.post(f"/api/classes/join/{course['code']}")
    teacher_id=client.get("/api/classes/{}/contacts".format(course["id"])).json()[0]["id"]
    sent=client.post(f"/api/classes/{course['id']}/messages",json={"recipient_id":teacher_id,"body":"Could you explain the lab?"})
    assert sent.status_code==200,sent.text
    login(client,"teacher@classflow.example.com")
    thread=client.get(f"/api/classes/{course['id']}/messages?peer_id={student_id}")
    assert thread.status_code==200 and thread.json()[0]["body"]=="Could you explain the lab?"
    assert client.post(f"/api/classes/{course['id']}/messages",json={"recipient_id":student_id,"body":"Please review page 4."}).status_code==200
    register(client,"Student Two","student2@classflow.example.com")
    client.post(f"/api/classes/join/{course['code']}")
    assert client.get(f"/api/classes/{course['id']}/messages?peer_id={student_id}").status_code==403

def test_qr_attendance_code_is_temporary_enrollment_scoped_and_idempotent(client):
    make_admin(client)
    course=make_teacher_and_class(client,"Chemistry")
    started=client.post(f"/api/classes/{course['id']}/attendance/sessions")
    assert started.status_code==200,started.text
    code=started.json()["code"]
    register(client,"Student One","student@classflow.example.com")
    client.post(f"/api/classes/join/{course['code']}")
    first=client.post(f"/api/classes/{course['id']}/attendance/check-in",json={"code":code})
    second=client.post(f"/api/classes/{course['id']}/attendance/check-in",json={"code":code})
    assert first.status_code==200 and second.status_code==200
    assert second.json()["message"]=="Your attendance is already recorded."
    login(client,"teacher@classflow.example.com")
    record=client.get(f"/api/classes/{course['id']}/attendance").json()[0]
    assert record["source"]=="qr" and record["status"]=="present"
    assert client.put(f"/api/classes/{course['id']}/attendance/sessions/{started.json()['id']}/close").status_code==200
    login(client,"student@classflow.example.com")
    assert client.post(f"/api/classes/{course['id']}/attendance/check-in",json={"code":code}).status_code==400

def test_user_can_upload_and_view_private_profile_picture(client):
    register(client,"Student One","student@classflow.example.com")
    uploaded=client.post("/api/profile/avatar",files={"file":("portrait.png",b"\x89PNG\r\n\x1a\nimage","image/png")})
    assert uploaded.status_code==200,uploaded.text
    assert uploaded.json()["avatar_url"].startswith("/api/users/")
    response=client.get(uploaded.json()["avatar_url"])
    assert response.status_code==200 and response.content.startswith(b"\x89PNG")
    from urllib.parse import parse_qs,urlparse
    from app.main import UPLOADS
    avatar_name=parse_qs(urlparse(uploaded.json()["avatar_url"]).query)["v"][0]
    (UPLOADS/"avatars"/avatar_name).unlink(missing_ok=True)

def test_same_origin_lan_dev_proxy_is_allowed_but_foreign_origin_is_blocked(client):
    lan=client.post("/api/auth/register",headers={"origin":"http://192.168.1.25:5173","x-forwarded-host":"192.168.1.25:5173","x-forwarded-proto":"http"},json={})
    foreign=client.post("/api/auth/register",headers={"origin":"https://untrusted.example"},json={})
    assert lan.status_code==422
    assert foreign.status_code==403

def test_social_login_is_disabled_without_provider_credentials(client,monkeypatch):
    for key in ("GOOGLE_CLIENT_ID","GOOGLE_CLIENT_SECRET","FACEBOOK_CLIENT_ID","FACEBOOK_CLIENT_SECRET"):
        monkeypatch.delenv(key,raising=False)
    assert client.get("/api/auth/oauth/providers").json()=={"google":False,"facebook":False}
    response=client.get("/api/auth/oauth/google/start")
    assert response.status_code==503
    assert "not configured" in response.json()["detail"]

def test_virtual_class_host_moderation_and_history_clear_preserve_live_call(client):
    make_admin(client)
    course=make_teacher_and_class(client,"Design")
    register(client,"Student One","student@classflow.example.com")
    assert client.post(f"/api/classes/join/{course['code']}").status_code==200
    login(client,"teacher@classflow.example.com")
    room=client.post(f"/api/classes/{course['id']}/virtual-rooms",json={"title":"Studio session"}).json()
    teacher_presence=client.post(f"/api/virtual-rooms/{room['id']}/join").json()["presence_id"]
    login(client,"student@classflow.example.com")
    student_presence=client.post(f"/api/virtual-rooms/{room['id']}/join").json()["presence_id"]
    login(client,"teacher@classflow.example.com")
    host_command=client.post(f"/api/virtual-rooms/{room['id']}/signals",json={"sender_presence_id":teacher_presence,"recipient_presence_id":student_presence,"payload":{"kind":"command","command":"mute-audio"}})
    assert host_command.status_code==200,host_command.text
    login(client,"student@classflow.example.com")
    received=client.get(f"/api/virtual-rooms/{room['id']}/signals",params={"presence_id":student_presence,"after":0})
    assert received.status_code==200 and received.json()[0]["from_role"]=="teacher"
    denied=client.post(f"/api/virtual-rooms/{room['id']}/signals",json={"sender_presence_id":student_presence,"recipient_presence_id":teacher_presence,"payload":{"kind":"command","command":"remove"}})
    assert denied.status_code==403
    assert client.post(f"/api/virtual-rooms/{room['id']}/leave",json={"presence_id":student_presence}).status_code==200
    login(client,"teacher@classflow.example.com")
    cleared=client.delete(f"/api/classes/{course['id']}/virtual-attendance")
    assert cleared.status_code==200 and cleared.json()["cleared"]==1
    remaining=client.get(f"/api/classes/{course['id']}/virtual-attendance").json()
    assert len(remaining)==1 and remaining[0]["active"] is True
    assert client.post(f"/api/virtual-rooms/{room['id']}/heartbeat",json={"presence_id":teacher_presence}).status_code==200
