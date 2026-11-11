import { apiFetch, apiUrl, shouldDispatchSessionExpired } from "./api";
import { FormEvent, useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { BookOpen, Clock, Download, FileText, Grid2X2, Hand, LayoutPanelTop, LockKeyhole, Maximize, MessageSquare, Mic, MicOff, Minimize, MonitorUp, Paperclip, PhoneOff, Pin, Radio, Send, Shield, Smile, Sparkles, Users, Video, VideoOff, VolumeX, X } from "lucide-react";

type Room = { id: number; title: string; active: boolean; created: string; ended: string | null; participants: number; teacher: string };
type Participant = { id: number; user_id: number; name: string; role: string; avatar_url?: string | null; joined_at: string };
type AttendanceEntry = { room_id: number; title: string; student: string; role: string; joined_at: string; left_at: string | null; duration_seconds: number; active: boolean };
type ChatMessage = { id: string; sender_id: number; sender: string; body: string; created: string; attachment?: { material_id: number; name: string } };
type FloatingReaction = { id: string; emoji: string; left: number; rotation: number; size: number };
type MeetingPanel = "chat" | "people" | "resources" | "notes" | null;
type Props = { c: { id: number; name: string }; teacher: boolean; userName: string; userAvatarUrl?: string | null; onOpenProfile: () => void };

const api = async (path: string, options: RequestInit = {}) => {
  const response = await apiFetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && shouldDispatchSessionExpired()) window.dispatchEvent(new Event("classflow:session-expired"));
    throw new Error(data.detail || "Request failed");
  }
  return data;
};

function formatTime(value: string) {
  return new Date(value).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function formatDuration(seconds: number) {
  if (seconds < 60) return `${seconds} sec`;
  const minutes = Math.floor(seconds / 60);
  return minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)} hr ${minutes % 60} min`;
}

function formatCallDuration(seconds: number) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remaining = seconds % 60;
  return [hours, minutes, remaining].map(value => String(value).padStart(2, "0")).join(":");
}

function makeFloatingReaction(emoji: string): FloatingReaction {
  return { id: `${Date.now()}-${Math.random()}`, emoji, left: 18 + Math.random() * 64, rotation: Math.round(Math.random() * 28 - 14), size: Math.round(38 + Math.random() * 16) };
}

function VideoTile({ stream, name, avatarUrl, local = false, muted = false, cameraOff = false, effect = "natural", background = "studio", handRaised = false, reaction = null, screenSharing = false, speaking = false, audioMuted = false, pinned = false, onPin }: { stream: MediaStream | null; name: string; avatarUrl?: string | null; local?: boolean; muted?: boolean; cameraOff?: boolean; effect?: string; background?: string; handRaised?: boolean; reaction?: FloatingReaction | null; screenSharing?: boolean; speaking?: boolean; audioMuted?: boolean; pinned?: boolean; onPin?: () => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const [avatarAccent, setAvatarAccent] = useState("#3d5847");
  const videoStream = !cameraOff && stream?.getVideoTracks().length ? stream : null;
  useEffect(() => { if (video.current) video.current.srcObject = videoStream; }, [videoStream]);
  useEffect(() => {
    let active = true;
    const fallbackHue = [...name].reduce((value, character) => (value * 31 + character.charCodeAt(0)) % 360, 0);
    const fallbackColor = `hsl(${fallbackHue} 32% 31%)`;
    setAvatarAccent(fallbackColor);
    if (!avatarUrl) return () => { active = false; };
    const image = new Image();
    image.crossOrigin = "anonymous";
    image.onload = () => {
      if (!active) return;
      try {
        const canvas = document.createElement("canvas");
        canvas.width = 12; canvas.height = 12;
        const context = canvas.getContext("2d", { willReadFrequently: true });
        if (!context) return;
        context.drawImage(image, 0, 0, 12, 12);
        const pixels = context.getImageData(0, 0, 12, 12).data;
        let red = 0, green = 0, blue = 0, count = 0;
        for (let index = 0; index < pixels.length; index += 4) {
          if (pixels[index + 3] < 100) continue;
          red += pixels[index]; green += pixels[index + 1]; blue += pixels[index + 2]; count++;
        }
        if (count) setAvatarAccent(`rgb(${Math.round(red/count)}, ${Math.round(green/count)}, ${Math.round(blue/count)})`);
      } catch { setAvatarAccent(fallbackColor); }
    };
    image.onerror = () => { if (active) setAvatarAccent(fallbackColor); };
    image.src = apiUrl(avatarUrl);
    return () => { active = false; image.onload = null; image.onerror = null; };
  }, [avatarUrl, name]);
  return <div className={`virtual-video-tile virtual-bg-${background}${speaking ? " is-speaking" : ""}${pinned ? " is-pinned" : ""}${screenSharing ? " is-presenting" : ""}`}>
    {videoStream ? <video className={`video-effect-${effect}`} ref={video} autoPlay playsInline muted={muted} /> : <div className="virtual-video-placeholder" style={{ "--profile-accent": avatarAccent } as CSSProperties}>{avatarUrl?<img src={apiUrl(avatarUrl)} alt=""/>:<span>{name.trim().charAt(0).toUpperCase()}</span>}</div>}
    {handRaised && <span className="hand-raised-badge" title="Hand raised"><Hand size={15}/></span>}
    {reaction && <span className="reaction-float" key={reaction.id} style={{ left: `${reaction.left}%`, "--reaction-angle": `${reaction.rotation}deg`, "--reaction-size": `${reaction.size}px` } as CSSProperties}>{reaction.emoji}</span>}
    {screenSharing && <small className="screen-share-badge"><MonitorUp size={13}/> Presenting</small>}
    {onPin&&<button type="button" className="tile-pin-button" aria-label={pinned?"Unpin participant":"Pin participant"} title={pinned?"Unpin participant":"Pin participant"} onClick={onPin}><Pin size={15}/></button>}
    <span className="tile-status"><span>{name}{local ? " (You)" : ""}</span>{audioMuted&&<span className="tile-muted" title="Microphone off"><MicOff size={14}/></span>}</span>
  </div>;
}

export default function NativeClassroom({ c, teacher, userName, userAvatarUrl, onOpenProfile }: Props) {
  const [rooms, setRooms] = useState<Room[]>([]);
  const [entries, setEntries] = useState<AttendanceEntry[]>([]);
  const [room, setRoom] = useState<Room | null>(null);
  const [presenceId, setPresenceId] = useState<number | null>(null);
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [localStream, setLocalStream] = useState<MediaStream | null>(null);
  const [screenStream, setScreenStream] = useState<MediaStream | null>(null);
  const [remoteStreams, setRemoteStreams] = useState<Record<number, MediaStream>>({});
  const [title, setTitle] = useState("");
  const [muted, setMuted] = useState(false);
  const [cameraOff, setCameraOff] = useState(false);
  const [handRaised, setHandRaised] = useState(false);
  const [raisedHands, setRaisedHands] = useState<Record<number, boolean>>({});
  const [reactions, setReactions] = useState<Record<number, FloatingReaction>>({});
  const [cameraEffect, setCameraEffect] = useState("natural");
  const [cameraBackground, setCameraBackground] = useState("studio");
  const [cameraSettingsOpen, setCameraSettingsOpen] = useState(false);
  const [reactionPickerOpen, setReactionPickerOpen] = useState(false);
  const [sidePanel, setSidePanel] = useState<MeetingPanel>(null);
  const [layoutMode, setLayoutMode] = useState<"grid" | "spotlight">("grid");
  const [pinnedParticipant, setPinnedParticipant] = useState<number | null>(null);
  const [presentingParticipants, setPresentingParticipants] = useState<Record<number, boolean>>({});
  const [mediaStates, setMediaStates] = useState<Record<number, { muted: boolean; cameraOff: boolean }>>({});
  const [speakingParticipants, setSpeakingParticipants] = useState<Record<number, boolean>>({});
  const [unreadChat, setUnreadChat] = useState(0);
  const [resources, setResources] = useState<any[]>([]);
  const [notes, setNotes] = useState("");
  const [emojiPickerOpen, setEmojiPickerOpen] = useState(false);
  const [resourcePickerOpen, setResourcePickerOpen] = useState(false);
  const [chatDraft, setChatDraft] = useState("");
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [callSeconds, setCallSeconds] = useState(0);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [clearingHistory, setClearingHistory] = useState(false);
  const localStreamRef = useRef<MediaStream | null>(null);
  const screenStreamRef = useRef<MediaStream | null>(null);
  const meetingRef = useRef<HTMLElement | null>(null);
  const chatMessagesRef = useRef<HTMLDivElement | null>(null);
  const sidePanelRef = useRef<MeetingPanel>(null);
  const peers = useRef(new Map<number, RTCPeerConnection>());
  const pendingCandidates = useRef(new Map<number, RTCIceCandidateInit[]>());
  const signalCursor = useRef(0);
  const pollBusy = useRef(false);

  const refresh = useCallback(async () => {
    try {
      const [nextRooms, nextEntries] = await Promise.all([
        api(`/classes/${c.id}/virtual-rooms`),
        teacher ? api(`/classes/${c.id}/virtual-attendance`) : Promise.resolve([]),
      ]);
      setRooms(nextRooms);
      setEntries(nextEntries);
    } catch (failure: any) { setError(failure.message); }
  }, [c.id, teacher]);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => { void refresh(); }, 10000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    let active = true;
    api(`/classes/${c.id}/materials`).then((items: any[]) => { if (active) setResources(items); }).catch(() => {});
    return () => { active = false; };
  }, [c.id]);

  useEffect(() => {
    const key = `classflow-meeting-notes-${c.id}`;
    setNotes(localStorage.getItem(key) || "");
  }, [c.id]);

  useEffect(() => {
    sidePanelRef.current = sidePanel;
    if (sidePanel === "chat") setUnreadChat(0);
  }, [sidePanel]);

  const sendSignal = useCallback(async (recipientId: number, payload: Record<string, unknown>) => {
    if (!room || presenceId === null) return;
    await api(`/virtual-rooms/${room.id}/signals`, { method: "POST", body: JSON.stringify({ sender_presence_id: presenceId, recipient_presence_id: recipientId, payload }) });
  }, [room, presenceId]);

  const broadcast = useCallback(async (payload: Record<string, unknown>) => {
    await Promise.all(participants.filter(person => person.id !== presenceId).map(person => sendSignal(person.id, payload)));
  }, [participants, presenceId, sendSignal]);

  const ensurePeer = useCallback(async (participant: Participant) => {
    if (presenceId === null || participant.id === presenceId || peers.current.has(participant.id)) return peers.current.get(participant.id);
    const connection = new RTCPeerConnection({ iceServers: [{ urls: ["stun:stun.l.google.com:19302", "stun:stun1.l.google.com:19302"] }] });
    peers.current.set(participant.id, connection);
    const audioTracks = localStream?.getAudioTracks() || [];
    const videoTrack = screenStream?.getVideoTracks()[0] || localStream?.getVideoTracks()[0];
    audioTracks.forEach(track => connection.addTrack(track, localStream!));
    if (!audioTracks.length) connection.addTransceiver("audio", { direction: "recvonly" });
    if (videoTrack) connection.addTrack(videoTrack, screenStream || localStream!);
    else connection.addTransceiver("video", { direction: "recvonly" });
    connection.onicecandidate = event => {
      if (event.candidate) void sendSignal(participant.id, { candidate: event.candidate.toJSON() }).catch(() => {});
    };
    connection.ontrack = event => {
      const stream = event.streams[0];
      if (stream) setRemoteStreams(current => ({ ...current, [participant.id]: stream }));
    };
    connection.onconnectionstatechange = () => {
      if (["failed", "closed"].includes(connection.connectionState)) {
        setRemoteStreams(current => { const next = { ...current }; delete next[participant.id]; return next; });
      }
    };
    if (presenceId < participant.id) {
      const offer = await connection.createOffer();
      await connection.setLocalDescription(offer);
      await sendSignal(participant.id, { description: connection.localDescription?.toJSON() || offer });
    }
    return connection;
  }, [localStream, presenceId, screenStream, sendSignal]);

  useEffect(() => {
    if (!room || presenceId === null) return;
    participants.filter(person => person.id !== presenceId).forEach(person => { void ensurePeer(person).catch(failure => setError(failure.message)); });
  }, [room?.id, presenceId, participants, ensurePeer]);

  const leave = useCallback(async (notify = true) => {
    const oldRoom = room;
    const oldPresence = presenceId;
    if (notify && oldRoom && oldPresence !== null) {
      try { await api(`/virtual-rooms/${oldRoom.id}/leave`, { method: "POST", body: JSON.stringify({ presence_id: oldPresence }) }); } catch { /* The heartbeat expires if the connection is already gone. */ }
    }
    peers.current.forEach(connection => connection.close());
    peers.current.clear();
    pendingCandidates.current.clear();
    localStream?.getTracks().forEach(track => track.stop());
    screenStreamRef.current?.getTracks().forEach(track => track.stop());
    screenStreamRef.current = null;
    localStreamRef.current = null;
    setLocalStream(null); setScreenStream(null); setRemoteStreams({}); setPresenceId(null); setParticipants([]); setRoom(null); setMuted(false); setCameraOff(false); setHandRaised(false); setRaisedHands({}); setReactions({}); setPinnedParticipant(null); setPresentingParticipants({}); setMediaStates({}); setSpeakingParticipants({}); setSidePanel(null); sidePanelRef.current = null; setChatMessages([]); setUnreadChat(0); setEmojiPickerOpen(false); setResourcePickerOpen(false); setCameraSettingsOpen(false); setReactionPickerOpen(false);
    void refresh();
  }, [localStream, presenceId, refresh, room]);

  const stopScreenShare = useCallback(async () => {
    const currentScreen = screenStreamRef.current;
    if (!currentScreen) return;
    screenStreamRef.current = null;
    const cameraTrack = localStreamRef.current?.getVideoTracks()[0] || null;
    try {
      await Promise.all([...peers.current.values()].map(async connection => {
        const sender = connection.getSenders().find(item => item.track?.kind === "video")
          || connection.getTransceivers().find(item => item.receiver.track.kind === "video")?.sender;
        if (sender) await sender.replaceTrack(cameraTrack);
      }));
    } catch (failure: any) { setError(failure.message); }
    currentScreen.getTracks().forEach(track => track.stop());
    setScreenStream(null);
    void broadcast({ kind: "presenting", active: false }).catch(failure => setError(failure.message));
  }, [broadcast]);

  const toggleScreenShare = async () => {
    if (screenStreamRef.current) { await stopScreenShare(); return; }
    if (!navigator.mediaDevices?.getDisplayMedia) {
      setError("Screen sharing is not available in this browser or app.");
      return;
    }
    try {
      const display = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
      const track = display.getVideoTracks()[0];
      screenStreamRef.current = display;
      setScreenStream(display);
      void broadcast({ kind: "presenting", active: true }).catch(failure => setError(failure.message));
      track.addEventListener("ended", () => { void stopScreenShare(); }, { once: true });
      await Promise.all([...peers.current.entries()].map(async ([participantId, connection]) => {
        const videoTransceiver = connection.getTransceivers().find(item => item.receiver.track.kind === "video");
        const sender = connection.getSenders().find(item => item.track?.kind === "video") || videoTransceiver?.sender;
        if (sender) {
          const needsNegotiation = videoTransceiver?.direction === "recvonly" || videoTransceiver?.direction === "inactive";
          if (needsNegotiation && videoTransceiver) videoTransceiver.direction = "sendrecv";
          await sender.replaceTrack(track);
          if (needsNegotiation) {
            const offer = await connection.createOffer();
            await connection.setLocalDescription(offer);
            await sendSignal(participantId, { description: connection.localDescription?.toJSON() || offer });
          }
          return;
        }
        connection.addTrack(track, display);
        const offer = await connection.createOffer();
        await connection.setLocalDescription(offer);
        await sendSignal(participantId, { description: connection.localDescription?.toJSON() || offer });
      }));
    } catch (failure: any) {
      if (failure.name !== "AbortError" && failure.name !== "NotAllowedError") setError(failure.message || "Could not start screen sharing.");
    }
  };

  const sendChat = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const body = chatDraft.trim();
    if (!body || presenceId === null) return;
    setChatDraft("");
    setChatMessages(current => [...current.slice(-99), {
      id: `local-${Date.now()}`,
      sender_id: presenceId,
      sender: "You",
      body,
      created: new Date().toISOString(),
    }]);
    try { await broadcast({ kind: "chat", body }); }
    catch (failure: any) { setError(failure.message); }
  };

  const selectPanel = (panel: MeetingPanel) => {
    sidePanelRef.current = panel;
    setSidePanel(panel);
    if (panel === "chat") setUnreadChat(0);
  };

  const openPanel = (panel: Exclude<MeetingPanel, null>) => selectPanel(sidePanel === panel ? null : panel);

  const sendResource = async (resource: any) => {
    if (presenceId === null) return;
    const attachment = { material_id: Number(resource.id), name: String(resource.name) };
    const message: ChatMessage = {
      id: `local-${Date.now()}`,
      sender_id: presenceId,
      sender: "You",
      body: "Shared a class resource",
      created: new Date().toISOString(),
      attachment,
    };
    setChatMessages(current => [...current.slice(-99), message]);
    setResourcePickerOpen(false);
    selectPanel("chat");
    try { await broadcast({ kind: "chat", body: message.body, attachment }); }
    catch (failure: any) { setError(failure.message); }
  };

  const updateNotes = (value: string) => {
    setNotes(value);
    localStorage.setItem(`classflow-meeting-notes-${c.id}`, value);
  };

  const toggleFullscreen = async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await meetingRef.current?.requestFullscreen();
    } catch (failure: any) { setError(failure.message); }
  };

  useEffect(() => {
    if (!room || presenceId === null) return;
    const roomId = room.id; const currentPresence = presenceId;
    const markLeft = () => apiFetch(`/virtual-rooms/${roomId}/leave`, { method: "POST", keepalive: true, body: JSON.stringify({ presence_id: currentPresence }) }).catch(() => {});
    const onPageHide = () => { void markLeft(); };
    window.addEventListener("pagehide", onPageHide);
    return () => {
      window.removeEventListener("pagehide", onPageHide);
      void markLeft();
      peers.current.forEach(connection => connection.close()); peers.current.clear();
      localStreamRef.current?.getTracks().forEach(track => track.stop()); localStreamRef.current = null;
      screenStreamRef.current?.getTracks().forEach(track => track.stop()); screenStreamRef.current = null;
    };
  }, [room?.id, presenceId]);

  useEffect(() => {
    if (!room || presenceId === null) return;
    let cancelled = false;
    const poll = async () => {
      if (pollBusy.current) return;
      pollBusy.current = true;
      try {
        const [state, signals] = await Promise.all([
          api(`/virtual-rooms/${room.id}/state`),
          api(`/virtual-rooms/${room.id}/signals?presence_id=${presenceId}&after=${signalCursor.current}`),
          api(`/virtual-rooms/${room.id}/heartbeat`, { method: "POST", body: JSON.stringify({ presence_id: presenceId }) }),
        ]);
        if (cancelled) return;
        const activeIds = new Set<number>(state.participants.map((person: Participant) => person.id));
        const departed = [...peers.current.keys()].filter(id => !activeIds.has(id));
        departed.forEach(id => { peers.current.get(id)?.close(); peers.current.delete(id); pendingCandidates.current.delete(id); });
        if (departed.length) {
          setRemoteStreams(current => Object.fromEntries(Object.entries(current).filter(([id]) => !departed.includes(Number(id)))));
          setPresentingParticipants(current => Object.fromEntries(Object.entries(current).filter(([id]) => !departed.includes(Number(id)))));
          setMediaStates(current => Object.fromEntries(Object.entries(current).filter(([id]) => !departed.includes(Number(id)))));
          setRaisedHands(current => Object.fromEntries(Object.entries(current).filter(([id]) => !departed.includes(Number(id)))));
          setReactions(current => Object.fromEntries(Object.entries(current).filter(([id]) => !departed.includes(Number(id)))));
        }
        setParticipants(state.participants);
        if (!state.room.active) {
          setError("The teacher ended this virtual class.");
          await leave(false);
          return;
        }
        for (const signal of signals) {
          signalCursor.current = Math.max(signalCursor.current, signal.id);
          if (signal.payload.kind === "chat" && typeof signal.payload.body === "string") {
            const rawAttachment = signal.payload.attachment as { material_id?: unknown; name?: unknown } | undefined;
            const attachment = rawAttachment && typeof rawAttachment.material_id === "number" && Number.isInteger(rawAttachment.material_id) && typeof rawAttachment.name === "string"
              ? { material_id: rawAttachment.material_id, name: rawAttachment.name }
              : undefined;
            setChatMessages(current => [...current.slice(-99), {
              id: String(signal.id),
              sender_id: signal.from_presence_id,
              sender: signal.from_name,
              body: signal.payload.body as string,
              created: new Date().toISOString(),
              attachment,
            }]);
            if (sidePanelRef.current !== "chat") setUnreadChat(current => current + 1);
            continue;
          }
          if (signal.payload.kind === "presenting") {
            setPresentingParticipants(current => ({ ...current, [signal.from_presence_id]: Boolean(signal.payload.active) }));
            continue;
          }
          if (signal.payload.kind === "media-state") {
            setMediaStates(current => ({ ...current, [signal.from_presence_id]: { muted: Boolean(signal.payload.muted), cameraOff: Boolean(signal.payload.cameraOff) } }));
            continue;
          }
          if (signal.payload.kind === "hand") {
            setRaisedHands(current => ({ ...current, [signal.from_presence_id]: Boolean(signal.payload.raised) }));
            continue;
          }
          if (signal.payload.kind === "reaction" && typeof signal.payload.emoji === "string") {
            const reaction = makeFloatingReaction(signal.payload.emoji);
            reaction.id = String(signal.id);
            setReactions(current => ({ ...current, [signal.from_presence_id]: reaction }));
            window.setTimeout(() => setReactions(current => {
              if (current[signal.from_presence_id]?.id !== reaction.id) return current;
              const next = { ...current };
              delete next[signal.from_presence_id];
              return next;
            }), 2600);
            continue;
          }
          if (signal.payload.kind === "command") {
            if (signal.from_role !== "teacher" && signal.from_role !== "admin") continue;
            const command = signal.payload.command;
            if (command === "mute-audio") {
              localStreamRef.current?.getAudioTracks().forEach(track => { track.enabled = false; });
              setMuted(true);
              setMediaStates(current => ({ ...current, [presenceId]: { muted: true, cameraOff: current[presenceId]?.cameraOff || false } }));
              await Promise.all(state.participants.filter((person: Participant) => person.id !== presenceId).map((person: Participant) => sendSignal(person.id, { kind: "media-state", muted: true, cameraOff: mediaStates[presenceId]?.cameraOff || false })));
            } else if (command === "stop-video") {
              localStreamRef.current?.getVideoTracks().forEach(track => { track.enabled = false; });
              setCameraOff(true);
              setMediaStates(current => ({ ...current, [presenceId]: { muted: current[presenceId]?.muted || false, cameraOff: true } }));
              await Promise.all(state.participants.filter((person: Participant) => person.id !== presenceId).map((person: Participant) => sendSignal(person.id, { kind: "media-state", muted: mediaStates[presenceId]?.muted || false, cameraOff: true })));
            } else if (command === "remove") {
              setError("The host removed you from this class.");
              await leave(false);
            }
            continue;
          }
          const person = state.participants.find((item: Participant) => item.id === signal.from_presence_id) || { id: signal.from_presence_id, name: signal.from_name, role: "student", user_id: 0, joined_at: "" };
          const connection = await ensurePeer(person);
          if (!connection) continue;
          if (signal.payload.description) {
            await connection.setRemoteDescription(signal.payload.description);
            const queued = pendingCandidates.current.get(person.id) || [];
            for (const candidate of queued) await connection.addIceCandidate(candidate);
            pendingCandidates.current.delete(person.id);
            if (signal.payload.description.type === "offer") {
              const answer = await connection.createAnswer();
              await connection.setLocalDescription(answer);
              await sendSignal(person.id, { description: connection.localDescription?.toJSON() || answer });
            }
          } else if (signal.payload.candidate) {
            if (connection.remoteDescription) await connection.addIceCandidate(signal.payload.candidate);
            else pendingCandidates.current.set(person.id, [...(pendingCandidates.current.get(person.id) || []), signal.payload.candidate]);
          }
        }
      } catch (failure: any) { if (!cancelled) setError(failure.message); }
      finally { pollBusy.current = false; }
    };
    signalCursor.current = 0;
    void poll();
    const timer = window.setInterval(() => { void poll(); }, 2000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [room?.id, presenceId, ensurePeer, leave, sendSignal]);

  const enter = async (selected: Room) => {
    setBusy(true); setError("");
    let stream: MediaStream | null = null;
    let mediaWarning = "";
    try {
      try {
        if (!navigator.mediaDevices?.getUserMedia) throw new Error("Camera and microphone need a secure HTTPS connection on your phone.");
        stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: { facingMode: "user" } });
      } catch (failure: any) {
        try {
          if (!navigator.mediaDevices?.getUserMedia) throw failure;
          stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
          mediaWarning = "Camera access was unavailable. You joined with microphone audio only.";
        } catch {
          mediaWarning = `${failure.message || "Camera or microphone access was denied."} You can still join in listen-only mode.`;
        }
      }
      const joined = await api(`/virtual-rooms/${selected.id}/join`, { method: "POST" });
      localStreamRef.current = stream; setLocalStream(stream); setRoom(selected); setPresenceId(joined.presence_id); setParticipants(joined.participants);
      setError(mediaWarning);
      setRooms(current => current.map(item => item.id === selected.id ? { ...item, participants: item.participants + 1 } : item));
    } catch (failure: any) { stream?.getTracks().forEach(track => track.stop()); localStreamRef.current = null; setLocalStream(null); setError(failure.message); }
    finally { setBusy(false); }
  };

  const start = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const created = await api(`/classes/${c.id}/virtual-rooms`, { method: "POST", body: JSON.stringify({ title: title.trim() || `${c.name} live class` }) });
      setTitle(""); await refresh(); await enter({ ...created, teacher: "You", participants: 0 });
    } catch (failure: any) { setError(failure.message); }
    finally { setBusy(false); }
  };

  const closeRoom = async (id: number) => {
    try { await api(`/virtual-rooms/${id}/close`, { method: "PUT" }); if (room?.id === id) await leave(false); await refresh(); }
    catch (failure: any) { setError(failure.message); }
  };

  const clearRoomHistory = async () => {
    if (!rooms.some(item => !item.active) || clearingHistory) return;
    if (!window.confirm("Clear all ended virtual classroom sessions from this list? Live classes and attendance records will remain.")) return;
    setClearingHistory(true); setError("");
    try { await api(`/classes/${c.id}/virtual-rooms`, { method: "DELETE" }); await refresh(); }
    catch (failure: any) { setError(failure.message); }
    finally { setClearingHistory(false); }
  };

  const toggleAudio = () => { const next = !muted; localStream?.getAudioTracks().forEach(track => { track.enabled = !next; }); setMuted(next); void broadcast({ kind: "media-state", muted: next, cameraOff }).catch(failure => setError(failure.message)); };
  const toggleVideo = () => { const next = !cameraOff; localStream?.getVideoTracks().forEach(track => { track.enabled = !next; }); setCameraOff(next); void broadcast({ kind: "media-state", muted, cameraOff: next }).catch(failure => setError(failure.message)); };
  const toggleHand = () => {
    const next = !handRaised;
    setHandRaised(next);
    void broadcast({ kind: "hand", raised: next }).catch(failure => setError(failure.message));
  };
  const sendReaction = (emoji: string) => {
    if (presenceId === null) return;
    const reaction = makeFloatingReaction(emoji);
    setReactions(current => ({ ...current, [presenceId]: reaction }));
    window.setTimeout(() => {
      setReactions(current => {
        if (current[presenceId]?.id !== reaction.id) return current;
        const next = { ...current };
        delete next[presenceId];
        return next;
      });
    }, 2600);
    void broadcast({ kind: "reaction", emoji, id: reaction.id }).catch(failure => setError(failure.message));
  };
  const hostCommand = async (target: number, command: "mute-audio" | "stop-video" | "remove") => {
    try { await sendSignal(target, { kind: "command", command }); }
    catch (failure: any) { setError(failure.message); }
  };
  const muteEveryone = async () => {
    try { await Promise.all(participants.filter(person => person.id !== presenceId).map(person => sendSignal(person.id, { kind: "command", command: "mute-audio" }))); }
    catch (failure: any) { setError(failure.message); }
  };

  useEffect(() => {
    const updateFullscreen = () => setIsFullscreen(document.fullscreenElement === meetingRef.current);
    document.addEventListener("fullscreenchange", updateFullscreen);
    return () => document.removeEventListener("fullscreenchange", updateFullscreen);
  }, []);

  useEffect(() => {
    if (!room) { setCallSeconds(0); return; }
    const update = () => setCallSeconds(Math.max(0, Math.floor((Date.now() - new Date(room.created).getTime()) / 1000)));
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, [room]);

  useEffect(() => {
    if (sidePanel === "chat") chatMessagesRef.current?.scrollTo({ top: chatMessagesRef.current.scrollHeight });
  }, [chatMessages, sidePanel]);

  useEffect(() => {
    if (!room || presenceId === null || typeof AudioContext === "undefined") return;
    // Measure audio levels locally so the active speaker can be spotlighted without uploading analysis data.
    const context = new AudioContext();
    const streams = [
      { id: presenceId, stream: localStream },
      ...participants.filter(person => person.id !== presenceId).map(person => ({ id: person.id, stream: remoteStreams[person.id] || null })),
    ].filter((item): item is { id: number; stream: MediaStream } => Boolean(item.stream?.getAudioTracks().length));
    const analysers = streams.map(item => {
      const analyser = context.createAnalyser();
      analyser.fftSize = 512;
      context.createMediaStreamSource(item.stream).connect(analyser);
      return { id: item.id, analyser, samples: new Uint8Array(analyser.fftSize) };
    });
    void context.resume().catch(() => {});
    const timer = window.setInterval(() => {
      const next: Record<number, boolean> = {};
      analysers.forEach(({ id, analyser, samples }) => {
        analyser.getByteTimeDomainData(samples);
        const level = Math.sqrt(samples.reduce((sum, sample) => sum + (sample - 128) ** 2, 0) / samples.length);
        next[id] = level > 7;
      });
      setSpeakingParticipants(current => {
        const unchanged = Object.keys(next).length === Object.keys(current).length && Object.entries(next).every(([id, value]) => current[Number(id)] === value);
        return unchanged ? current : next;
      });
    }, 140);
    return () => { window.clearInterval(timer); void context.close().catch(() => {}); };
  }, [room?.id, presenceId, localStream, remoteStreams, participants]);

  const selfId = presenceId ?? -1;
  const tiles = [
    {
      id: selfId,
      element: <VideoTile stream={screenStream || localStream} name={screenStream ? "Your screen" : "You"} avatarUrl={userAvatarUrl} local muted cameraOff={cameraOff&&!screenStream} effect={screenStream ? "natural" : cameraEffect} background={screenStream ? "studio" : cameraBackground} handRaised={handRaised} reaction={reactions[selfId]||null} screenSharing={Boolean(screenStream)} speaking={Boolean(speakingParticipants[selfId])} audioMuted={muted} pinned={pinnedParticipant===selfId} onPin={()=>setPinnedParticipant(current=>current===selfId?null:selfId)}/> ,
    },
    ...participants.filter(person => person.id !== presenceId).map(person => ({
      id: person.id,
      element: <VideoTile key={person.id} stream={remoteStreams[person.id] || null} name={person.name} avatarUrl={person.avatar_url} cameraOff={Boolean(mediaStates[person.id]?.cameraOff)} handRaised={Boolean(raisedHands[person.id])} reaction={reactions[person.id]||null} screenSharing={Boolean(presentingParticipants[person.id])} speaking={Boolean(speakingParticipants[person.id])} audioMuted={Boolean(mediaStates[person.id]?.muted)} pinned={pinnedParticipant===person.id} onPin={()=>setPinnedParticipant(current=>current===person.id?null:person.id)}/>,
    })),
  ];
  const presentingId = screenStream ? selfId : participants.find(person => presentingParticipants[person.id])?.id ?? null;
  const activeSpeakerId = Number(Object.keys(speakingParticipants).find(id => speakingParticipants[Number(id)]));
  // Presenter takes precedence over a manual pin; grid mode only focuses while content is being presented.
  const focusedId = presentingId ?? pinnedParticipant ?? (layoutMode === "spotlight" ? (Number.isFinite(activeSpeakerId) ? activeSpeakerId : selfId) : null);
  const focusedTile = tiles.find(tile => tile.id === focusedId);
  const filmstripTiles = focusedTile ? tiles.filter(tile => tile.id !== focusedTile.id) : tiles;

  return <div className="native-classroom">
    {error && <div className="error virtual-error">{error}</div>}
    {room ? <section className={`virtual-live${isFullscreen ? " virtual-live-fullscreen" : ""}`} ref={meetingRef}>
      <header className="meeting-header"><div className="meeting-brand"><span className="meeting-brand-mark"><BookOpen size={18}/></span><span><strong>Classflow</strong><small>{c.name}</small></span></div><div className="meeting-title"><span className="live-indicator"><i/> LIVE</span><div><h3>{room.title}</h3><small>{c.name}</small></div></div><div className="meeting-header-tools"><span className="meeting-secure"><LockKeyhole size={14}/> Encrypted media</span><span className="meeting-duration"><Clock size={15}/>{formatCallDuration(callSeconds)}</span><span className="meeting-participant-count"><Users size={15}/>{participants.length}</span><div className="meeting-layout-switch" role="group" aria-label="Video layout"><button type="button" className={layoutMode==="grid"?"selected":""} aria-pressed={layoutMode==="grid"} onClick={()=>setLayoutMode("grid")} title="Grid view"><Grid2X2 size={16}/><span>Grid</span></button><button type="button" className={layoutMode==="spotlight"?"selected":""} aria-pressed={layoutMode==="spotlight"} onClick={()=>setLayoutMode("spotlight")} title="Spotlight view"><LayoutPanelTop size={16}/><span>Spotlight</span></button></div><button type="button" className="meeting-header-icon" aria-label="Camera and meeting settings" title="Camera and meeting settings" onClick={()=>setCameraSettingsOpen(open=>!open)}><Sparkles size={16}/></button><button type="button" className="meeting-profile-button" onClick={onOpenProfile} title="Open profile settings"><span>{userName.trim().charAt(0).toUpperCase()}</span><strong>{userName.split(" ")[0]}</strong></button>{teacher&&<button type="button" className="secondary" onClick={()=>void muteEveryone()}><VolumeX size={15}/> Mute everyone</button>}{teacher&&<button type="button" className="danger-button" onClick={() => void closeRoom(room.id)}><PhoneOff size={16}/> End class</button>}</div></header>
      <div className={`meeting-stage${sidePanel ? " has-panel" : ""}${presentingId!==null ? " is-presenting" : ""}`}>
        {focusedTile ? <div className={`presentation-layout${filmstripTiles.length?"":" single-focus"}${presentingId!==null?" has-presentation":" is-spotlight"}`}><div className="meeting-focus-tile">{presentingId!==null&&<span className="presenting-label"><MonitorUp size={14}/>{presentingId===selfId?"Your presentation":"Class presentation"}</span>}{focusedTile.element}</div>{filmstripTiles.length>0&&<div className="meeting-filmstrip">{filmstripTiles.map(tile=>tile.element)}</div>}</div> : <div className={`virtual-video-grid layout-${layoutMode}`}>{tiles.map(tile=>tile.element)}</div>}
        {sidePanel&&<aside className={`meeting-side-panel${sidePanel==="chat"?" meeting-chat-panel":""}`}><div className="meeting-side-head"><div><small>CLASSROOM TOOLS</small><h4>{sidePanel==="chat"?"In-call chat":sidePanel==="people"?"People":sidePanel==="resources"?"Class resources":"My notes"}</h4></div><button type="button" aria-label="Close meeting panel" onClick={()=>openPanel(sidePanel)}><X size={18}/></button></div><nav className="meeting-panel-tabs" aria-label="Classroom panels"><button type="button" className={sidePanel==="chat"?"selected":""} aria-pressed={sidePanel==="chat"} onClick={()=>openPanel("chat")}><MessageSquare size={15}/>Chat{unreadChat>0&&<span className="unread-badge">{unreadChat>99?"99+":unreadChat}</span>}</button><button type="button" className={sidePanel==="people"?"selected":""} aria-pressed={sidePanel==="people"} onClick={()=>openPanel("people")}><Users size={15}/>People<span className="tab-count">{participants.length}</span></button><button type="button" className={sidePanel==="resources"?"selected":""} aria-pressed={sidePanel==="resources"} onClick={()=>openPanel("resources")}><BookOpen size={15}/>Resources</button><button type="button" className={sidePanel==="notes"?"selected":""} aria-pressed={sidePanel==="notes"} onClick={()=>openPanel("notes")}><FileText size={15}/>Notes</button></nav>
          {sidePanel==="chat"&&<><div className="meeting-chat-list" ref={chatMessagesRef}>{chatMessages.length?chatMessages.map(message=><article className={`meeting-chat-message${message.sender_id===presenceId?" mine":""}`} key={message.id}><strong>{message.sender}</strong><p>{message.body}</p>{message.attachment&&<a className="meeting-attachment" href={apiUrl(`/classes/${c.id}/materials/${message.attachment.material_id}/download`)} target="_blank" rel="noreferrer"><Paperclip size={14}/>{message.attachment.name}<Download size={13}/></a>}<time>{new Date(message.created).toLocaleTimeString([], {hour:"numeric",minute:"2-digit"})}</time></article>):<div className="meeting-chat-empty"><MessageSquare size={24}/><strong>No messages yet</strong><span>Messages are shared with people in this call.</span></div>}</div><form className="meeting-chat-composer" onSubmit={sendChat}><div className="meeting-chat-composer-row"><button type="button" aria-label="Add emoji" title="Add emoji" onClick={()=>setEmojiPickerOpen(open=>!open)}><Smile size={17}/></button><button type="button" aria-label="Attach class resource" title="Attach class resource" onClick={()=>setResourcePickerOpen(open=>!open)}><Paperclip size={17}/></button><input value={chatDraft} onChange={event=>setChatDraft(event.target.value)} placeholder="Send a message" maxLength={1000} aria-label="In-call message"/><button className="meeting-send-button" type="submit" aria-label="Send message" disabled={!chatDraft.trim()}><Send size={17}/></button></div>{emojiPickerOpen&&<div className="meeting-emoji-picker">{["👏","❤️","😂","🎉","✨","👍","🙌","🤔"].map(emoji=><button type="button" key={emoji} onClick={()=>setChatDraft(current=>current+emoji)}>{emoji}</button>)}</div>}{resourcePickerOpen&&<div className="meeting-resource-picker">{resources.length?resources.map(resource=><button type="button" key={resource.id} onClick={()=>void sendResource(resource)}><Paperclip size={14}/><span>{resource.name}</span></button>):<small>No class resources available to attach.</small>}</div>}</form><p className="meeting-panel-note">In-call messages are visible while participants are connected.</p></>}
          {sidePanel==="people"&&<><div className="meeting-people-list">{participants.map(person=><article className="meeting-person" key={person.id}><span className="meeting-avatar">{person.name.trim().charAt(0).toUpperCase()}</span><span className="meeting-person-copy"><strong>{person.name}{person.id===presenceId?" (You)":""}</strong><small>{person.role}{raisedHands[person.id]?" · Hand raised":""}</small></span>{raisedHands[person.id]&&<Hand size={16} className="roster-hand"/>}{mediaStates[person.id]?.muted&&<span className="participant-state-icon" aria-label="Microphone off"><MicOff size={14}/></span>}{mediaStates[person.id]?.cameraOff&&<span className="participant-state-icon" aria-label="Camera off"><VideoOff size={14}/></span>}{teacher&&person.id!==presenceId&&<div className="meeting-person-actions"><button type="button" title="Mute participant" onClick={()=>void hostCommand(person.id,"mute-audio")}><VolumeX size={15}/></button><button type="button" title="Turn off participant camera" onClick={()=>void hostCommand(person.id,"stop-video")}><VideoOff size={15}/></button><button type="button" title="Remove participant" onClick={()=>void hostCommand(person.id,"remove")}><Shield size={15}/></button></div>}</article>)}</div><p className="meeting-panel-note">Attendance is recorded automatically.</p></>}
          {sidePanel==="resources"&&<div className="meeting-resources-list">{resources.length?resources.map(resource=><article className="meeting-resource" key={resource.id}><span><FileText size={17}/></span><div><strong>{resource.name}</strong><small>{Math.max(1,Math.ceil(resource.size/1024))} KB · {formatTime(resource.created)}</small></div><a href={apiUrl(`/classes/${c.id}/materials/${resource.id}/download`)} target="_blank" rel="noreferrer" aria-label={`Download ${resource.name}`}><Download size={16}/></a></article>):<div className="meeting-chat-empty"><BookOpen size={24}/><strong>No shared resources</strong><span>Files shared with this class will appear here.</span></div>}</div>}
          {sidePanel==="notes"&&<div className="meeting-notes-panel"><label htmlFor="meeting-notes">Personal notes</label><textarea id="meeting-notes" value={notes} onChange={event=>updateNotes(event.target.value)} placeholder="Write notes for this class…"/><small>Saved on this device for {c.name}.</small></div>}
        </aside>}
      </div>
      <div className="virtual-controls" role="toolbar" aria-label="Classroom controls"><button type="button" className={muted ? "control-button off" : "control-button"} onClick={toggleAudio} disabled={!localStream}>{muted ? <MicOff/> : <Mic/>}<span>{muted ? "Unmute" : "Mute"}</span></button><button type="button" className={cameraOff ? "control-button off" : "control-button"} onClick={toggleVideo} disabled={!localStream}>{cameraOff ? <VideoOff/> : <Video/>}<span>{cameraOff ? "Camera on" : "Camera off"}</span></button><button type="button" className={`control-button${screenStream?" off":""}`} onClick={()=>void toggleScreenShare()}><MonitorUp/><span>{screenStream?"Stop presenting":"Present"}</span></button><button type="button" className={`control-button${handRaised?" off":""}`} onClick={toggleHand}><Hand/><span>{handRaised?"Lower hand":"Raise hand"}</span></button><button type="button" className={`control-button${reactionPickerOpen ? " active" : ""}`} onClick={()=>{setReactionPickerOpen(open=>!open); setCameraSettingsOpen(false);}} aria-label="Open reactions"><Smile size={16}/><span>React</span></button>{reactionPickerOpen && <div className="reaction-mini-picker">{["👏","❤️","😂","🎉","✨","👍","🙌","🤔"].map(emoji=><button type="button" className="reaction-mini-button" key={emoji} onClick={()=>{sendReaction(emoji); setReactionPickerOpen(false);}} aria-label={`React ${emoji}`}>{emoji}</button>)}</div>}<button type="button" className={`control-button${cameraSettingsOpen ? " active" : ""}`} onClick={()=>{setCameraSettingsOpen(open=>!open); setReactionPickerOpen(false);}} aria-label="Camera settings"><Sparkles size={16}/><span>Effects</span></button>{cameraSettingsOpen && <><label className="mini-select"><span>Filter</span><select value={cameraEffect} onChange={event=>setCameraEffect(event.target.value)}><option value="natural">Natural</option><option value="warm">Golden hour</option><option value="mono">Monochrome</option><option value="soft">Soft focus</option></select></label><label className="mini-select"><span>Bg</span><select value={cameraBackground} onChange={event=>setCameraBackground(event.target.value)}><option value="studio">Studio</option><option value="aurora">Aurora</option><option value="sunset">Sunset</option><option value="ocean">Ocean</option></select></label></>}<button type="button" className={`control-button${sidePanel==="people"?" active":""}`} aria-pressed={sidePanel==="people"} onClick={()=>openPanel("people")}><Users/><span>People</span></button><button type="button" className={`control-button${sidePanel==="chat"?" active":""}`} aria-pressed={sidePanel==="chat"} onClick={()=>openPanel("chat")}><MessageSquare/><span>Chat</span>{unreadChat>0&&<span className="control-unread-badge">{unreadChat>99?"99+":unreadChat}</span>}</button><button type="button" className="control-icon-button" onClick={()=>void toggleFullscreen()} aria-label={isFullscreen?"Exit full screen":"Enter full screen"} title={isFullscreen?"Exit full screen":"Full screen"}>{isFullscreen?<Minimize/>:<Maximize/>}</button><button type="button" className="control-button leave-control" onClick={() => void leave()}><PhoneOff/><span>Leave</span></button></div>
      <p className="virtual-record-note"><Clock size={14}/> Your join time and time connected are being recorded for attendance.</p>
    </section> : <>
      {teacher && <section className="virtual-start-card"><div className="virtual-start-copy"><span className="virtual-start-icon"><Video/></span><div><h3>Start an online class</h3><p>Open a live audio and video room for enrolled students.</p></div></div><form className="virtual-start-form" onSubmit={start}><input value={title} onChange={event => setTitle(event.target.value)} placeholder={`${c.name} live class`} maxLength={180} aria-label="Classroom title"/><button className="primary" disabled={busy}><Radio size={16}/>{busy ? "Starting…" : "Start class"}</button></form></section>}
      <section className="virtual-room-list"><div className="virtual-section-head"><div><small>CLASSROOM SESSIONS</small><h3>{teacher ? "Live and recent classes" : "Live classes"}</h3></div><div className="virtual-list-actions"><button className="secondary" onClick={() => void refresh()}>Refresh</button>{teacher&&<button type="button" className="text-button danger-text" disabled={clearingHistory||!rooms.some(item=>!item.active)} onClick={()=>void clearRoomHistory()}>{clearingHistory?"Clearing…":"Clear all"}</button>}</div></div>{rooms.length ? rooms.map(item => <article className="virtual-room-row" key={item.id}><span className={item.active ? "room-status live" : "room-status"}>{item.active ? <><i/> LIVE</> : "ENDED"}</span><div className="virtual-room-info"><strong>{item.title}</strong><small>{item.teacher} · Started {formatTime(item.created)}{item.active ? ` · ${item.participants} connected` : ""}</small></div>{item.active ? <button className="primary" disabled={busy} onClick={() => void enter(item)}>{busy ? "Joining…" : "Join class"}</button> : <span className="room-ended">Class ended</span>}{teacher && item.active && <button className="text-button" onClick={() => void closeRoom(item.id)}>End class</button>}</article>) : <div className="empty"><Radio/><b>No online classes right now</b><p>{teacher ? "Start a class and your students can join here." : "Your teacher's live classes will appear here."}</p></div>}</section>
      {teacher && <section className="virtual-attendance"><div className="virtual-section-head"><div><small>AUTO-RECORDED ATTENDANCE</small><h3>Class join history</h3></div><div className="attendance-actions"><span>{entries.length} joins</span>{entries.length>0&&<button type="button" className="text-button danger-text" onClick={async()=>{if(!window.confirm("Clear all virtual classroom join history for this class? This cannot be undone."))return;try{await api(`/classes/${c.id}/virtual-attendance`,{method:"DELETE"});setEntries([])}catch(failure:any){setError(failure.message)}}}>Clear all</button>}</div></div>{entries.length ? <div className="virtual-attendance-table"><div className="virtual-attendance-header"><span>Student</span><span>Class</span><span>Joined</span><span>Time connected</span></div>{entries.map((entry,index) => <div className="virtual-attendance-row" key={`${entry.room_id}-${entry.student}-${entry.joined_at}-${index}`}><strong>{entry.student}<small>{entry.role}</small></strong><span>{entry.title}</span><span>{formatTime(entry.joined_at)}</span><span>{entry.active ? "Connected now" : entry.left_at ? formatDuration(entry.duration_seconds) : "Connection lost"}</span></div>)}</div> : <div className="empty"><Clock/><b>No attendance yet</b><p>Each student's visit will be recorded here.</p></div>}</section>}
    </>}
  </div>;
}
