from pprint import pprint
from   .send_signed_message import authorized_fetch
from   . import activitystreams
from   . import tasks
from   . import webfinger
from   .activitystreams import ordered_collection, with_context
from   .absolute_url import absolute_reverse, absolute_resolve
from   .inbox import InboxHandler, InboxException
import bs4
from   django.conf import settings
from   django.core.files.base import ContentFile
from   django.db import models
from   django.dispatch import receiver
from   django.utils.module_loading import import_string
from   django.utils.timezone import now
from   django.contrib.auth.models import User
import functools
import json
from   pathlib import Path
import re
import urllib.parse
import uuid
from   django.core.files import File

def default_empty():
    return {}

class AbstractActor(models.Model):
    username = models.CharField(max_length = 100)
    domain = models.CharField(max_length = 200)

    class Meta:
        abstract = True

    def __str__(self):
        return f'@{self.username}@{self.domain}'

    def display_name(self):
        raise NotImplementedError

    def icon_url(self):
        raise NotImplementedError

    def get_absolute_url(self):
        raise NotImplementedError

    def get_followers_url(self):
        raise NotImplementedError

    def get_outbox_url(self):
        raise NotImplementedError

    def followers(self):
        raise NotImplementedError

    @property
    def qualified_name(self):
        return f'@{self.username}@{self.domain}'

    @property
    def private_key(self):
        return self.get_private_key()

    @property
    def public_key(self):
        return self.get_public_key()

    def get_private_key(self):
        raise NotImplementedError

    def get_public_key(self):
        raise NotImplementedError

#from django.core.files.storage import FileSystemStorage
def local_actor_dir(instance, filename):
    print(instance, filename)
    p = Path(settings.ACTORS_DIR) / instance.domain / instance.username
    p.mkdir(exist_ok = True, parents=True)
    return p / filename+">test"


class LocalActor(AbstractActor):
    owner = models.ForeignKey(User, related_name="activitypub_account", on_delete=models.CASCADE, null=True)
    private_key_file = models.FileField(upload_to = local_actor_dir)
    public_key_file = models.FileField(upload_to = local_actor_dir)
    actor_json_file = models.FileField(upload_to = local_actor_dir, null=True, blank=True)

    inbox_handler_cls = InboxHandler

    def fill_in_bits(self):
        self.actor_json_file.save(
            'actor.json', 
            ContentFile(json.dumps({
                "type": "Service",
                "preferredUsername": self.username,
                "name": self.username,
                "summary": ""
            }, indent = 4))
        )

        from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key
        from cryptography.hazmat.primitives import serialization
        private_key = generate_private_key(public_exponent=65537, key_size=2048)
        self.private_key_file.save(
            'private.key', 
            ContentFile(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ))
        )
        self.public_key_file.save(
            'public.key',
            ContentFile(private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            ))
        )


    @functools.cache
    def get_private_key(self):
        with self.private_key_file.open('rb') as f:
            return f.read()

    @functools.cache
    def get_public_key(self):
        with self.public_key_file.open('rb') as f:
            return f.read()

    @with_context([activitystreams.ACTIVITYSTREAMS_CONTEXT, activitystreams.SECURITY_CONTEXT])
    def actor_json(self):
        with self.actor_json_file.open() as f:
            data = json.load(f)

        data.update({
            "id": self.get_absolute_url(),
            "followers": self.get_followers_url(),
            "inbox": self.get_inbox_url(),
            "outbox": self.get_outbox_url(),
            "publicKey": {
                "id": self.get_public_key_url(),
                "owner": self.get_absolute_url(),
                "publicKeyPem": self.public_key.decode('utf-8'),
            }
        })

        return data

    def display_name(self):
        data = self.actor_json()
        return data.get('name', data.get('preferredUsername', self.username))

    def icon_url(self):
        data = self.actor_json()
        return data.get('icon', {}).get('url')

    def get_absolute_url(self):
        return absolute_reverse('user_profile', username=self.username, domain=self.domain)

    def get_inbox_url(self):
        return absolute_reverse('user_inbox', username=self.username, domain=self.domain)

    def get_followers_url(self):
        return absolute_reverse('user_followers', username=self.username, domain=self.domain)

    def get_outbox_url(self):
        return absolute_reverse('user_outbox', username=self.username, domain=self.domain)

    def send_to_followers(self, message):
        self.distribute_message(message, self.followers.all())

    def get_public_key_url(self):
        return self.get_absolute_url() + '#main-key'

    def send_signed_message(self, inbox_url, message):
        return tasks.send_message(inbox_url, message, self.private_key, self.get_public_key_url())

    @ordered_collection()
    def followers_json(self):
        followers = (f.get_absolute_url() for f in self.followers.all())
        return followers, self.followers.count(), self.get_followers_url()

    def send_to_inbox(self, remote_actor, message):
        message = message.copy()
        message['to'] = [remote_actor.get_absolute_url()]
        return self.send_signed_message(remote_actor.get_inbox_url(), message)

    def distribute_message(self, message, recipients):
        recipients = list(set(recipients))

        for recipient in recipients:
            self.send_to_inbox(recipient, message)

    def update_profile(self):
        message = activitystreams.add_context({
            "summary": f'{self.username} updated its profile',
            "type": 'Update',
            "actor": self.get_absolute_url(),
            "object": self.get_absolute_url(),
        })
        self.send_to_followers(message)

    def create_note(self, blog_json, **kwargs):
        note = Note.create(self, blog_json, **kwargs)

        self.send_to_followers(note.create_message())
        
        return note

    @ordered_collection()
    def outbox_json(self):
        return (n.note_json() for n in self.notes.all()), self.notes.count(), self.get_outbox_url()

class AccessToken(models.Model):
    actor = models.ForeignKey(LocalActor, related_name='access_tokens', on_delete=models.CASCADE)
    access_token = models.CharField(max_length=100)
    name = models.CharField(max_length=200)

class RemoteActorManager(models.Manager):
    def create_from_profile_data(self, profile_data):
        url = profile_data['id']
        username = profile_data['preferredUsername']
        domain = urllib.parse.urlparse(url).netloc
        return RemoteActor.objects.create(
            username = username,
            domain = domain,
            url = url, 
            profile = profile_data,
        )

    def get_by_url(self, actor, url):
        try:
            return self.get(url=url)
        except RemoteActor.DoesNotExist:
            profile_data = authorized_fetch(url, actor.private_key, actor.get_public_key_url())
            return self.create_from_profile_data(profile_data)

    def get_by_username_domain(self, username, domain):
        try:
            return self.get(username = username, domain = domain)
        except RemoteActor.DoesNotExist:
            remote_data = webfinger.webfinger(username, domain)
            return self.create_from_profile_data(remote_data['profile'])

class RemoteActor(AbstractActor):
    objects = RemoteActorManager()

    url = models.URLField(max_length = 500)
    profile = models.JSONField(default = default_empty)

    following = models.ManyToManyField(
        LocalActor, 
        related_name='followers', 
        through = 'Follower',
        through_fields = ('remote_actor', 'following')
    )

    def get_absolute_url(self):
        return self.url

    def icon_url(self):
        return self.profile.get('icon',{}).get('url')

    def get_inbox_url(self):
        return self.profile.get('inbox')

    def display_name(self):
        return self.profile.get('name')

class Follower(models.Model):
    remote_actor = models.ForeignKey(RemoteActor, related_name='following_relations', on_delete = models.CASCADE)
    following = models.ForeignKey(LocalActor, related_name='follow_relations', on_delete = models.CASCADE)
    follow_date = models.DateTimeField(auto_now = True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=('remote_actor','following'), name='unique_followers_per_actor')
        ]

reserved = ':\/\?#\[\]@!\$\&\'\(\)\*\+,;=\s'
re_mention = re.compile(r'(?<!\S)@(?P<username>[^'+reserved+']+)@(?P<domain>[^'+reserved+']+)(?<!\.)(?=$|\.|['+reserved+'])')

def nl2br(data):
    content = data.get('content', '')
    data['content'] = content.replace('\n', '\n<br>\n')

    return data

def apply_mentions(data):
    content = data.get('content', '')


    mentioned = []
    for m in re_mention.finditer(content):
        username = m.group('username')
        domain = m.group('domain')
        mentioned.append((username, domain))

    unique_mentioned = {}
    for (username, domain) in mentioned:
        try:
            remote_actor = RemoteActor.objects.get_by_username_domain(username, domain)
            unique_mentioned[(username, domain)] = remote_actor
        except Exception:
            pass

    def sub_mention(m):
        username = m.group('username')
        domain = m.group('domain')
        try:
            remote_actor = unique_mentioned[(username, domain)]
            return f'<a href="{remote_actor.get_absolute_url()}">@{username}@{domain}</a>'
        except KeyError:
            return m[0]

    content = re_mention.sub(sub_mention, content)

    data['content'] = content

    tags = data.setdefault('tag',[])

    for ((username, domain), account) in unique_mentioned.items():
        tags.append({
            "type": "Mention",
            "href": account.get_absolute_url(),
            "name": f"@{username}@{domain}",
        })

    return data

class NoteManager(models.Manager):
    def get_by_absolute_url(self, url):
        try:
            m = absolute_resolve(url)
        except Exception:
            raise Exception(f"Can't reverse URL {url}")
        if not m:
            raise Note.DoesNotExist

        uid = m.kwargs['uid']
        return self.get(uid=uid)
    
    def get_by_stub_url(self, url):
        try:
            return self.get(stub=url)
        except:
            pass
        stub = url.split("/")[-1]
        #print(f"full path: {fullpath}")
        """try:
            m = absolute_resolve(url)
        except Exception:
            raise Exception(f"Can't reverse URL {url}")
        if not m:
            raise Note.DoesNotExist
        print("MMMMMMMMMMMMMMMMM")
        print(m)
        uid = m.kwargs['uid']"""
        return self.get(stub=stub)

class Note(models.Model):
    objects = NoteManager()

    uid = models.UUIDField(default = uuid.uuid4, primary_key = True)
    stub = models.CharField(unique=True, max_length=100)
    local_actor = models.ForeignKey(LocalActor, on_delete = models.CASCADE, related_name='notes', null=True, blank=True)
    remote_actor = models.ForeignKey(RemoteActor, on_delete = models.CASCADE, related_name='notes', null=True, blank=True)
    data = models.JSONField()
    published_date = models.DateTimeField(auto_now_add = True)
    to = models.ManyToManyField(RemoteActor, related_name='received_notes', blank=True)
    likes = models.ManyToManyField(RemoteActor, related_name='likes', blank=True)
    announces = models.ManyToManyField(RemoteActor, related_name='announces', blank=True)
    public = models.BooleanField(default=True)
    mentions = models.ManyToManyField(LocalActor, related_name='mentions', blank=True)
    post_type = models.TextField(max_length=20)

    updated_at = models.DateTimeField(null = True, auto_now = True)

    in_reply_to = models.ForeignKey('self', null=True, blank=True, related_name='replies', on_delete=models.SET_NULL)

    filters = [nl2br, apply_mentions,]

    class Meta:
        ordering = ['-published_date']

    @property
    def actor(self):
        return self.local_actor if self.local_actor else self.remote_actor

    def get_stub_or_url(self):
        if self.stub.startswith("https"):
            return self.stub
        return self.get_absolute_url()

    def get_absolute_url(self):
        if self.local_actor:
            return absolute_reverse('note', username=self.local_actor.username, domain=self.local_actor.domain, uid=str(self.uid))

    def get_stub_url(self):
        #if self.local_actor:
        if self.stub.startswith("http"): return self.stub
        return absolute_reverse('note', username=self.local_actor.username, domain=self.local_actor.domain, stub=str(self.stub))
   
    def __str__(self):
        return bs4.BeautifulSoup(self.data.get('content',''), 'html.parser').text

    def content(self):
        return self.data.get('content')

    @classmethod
    def filter_data(cls, data):
        for fn in cls.filters:
            data = fn(data)

        return data

    @classmethod
    def create(cls, actor, blog_json=None, content=None, to = None, in_reply_to=None, extra_data = None):
        title_image = None
        def create_stub():
            if not blog_json:
                return str(uuid.uuid4())
            if blog_json["title"]:
                unsafe_stub = blog_json["title"][:50].lower()
            else:
                unsafe_stub = blog_json["body"][:50].lower()
            unsafe_stub = unsafe_stub.replace(" ", "_")
            safe_stub = "".join([c for c in unsafe_stub if c in 
                                   "abcdefghijklmnopqrstuvwxyz_"])
            return safe_stub

        stub = create_stub()

        if blog_json:
            title_image = blog_json.get("title_image", None)
            summary = blog_json.get("summary")
            if summary:
                body_content = summary
            else:
                body_content = blog_json["body"][:300]
            data = {
                'content': f"""<h1>{blog_json["title"]}</h1>
                            {body_content}<br><br>
                            <a href='{actor.get_absolute_url()}/notes/{stub}'>Read article</a>"""
            }
            data["type"] = "Article"

            data["veblen"] = blog_json
        if content:
            data = {"content": content}
        if in_reply_to:
            data["inReplyTo"] = str(in_reply_to.stub)
            data["@context"] = "https://www.w3.org/ns/activitystreams"
            data["type"] = "Reply"
        if extra_data:
            data.update(extra_data)

        if title_image:
            del blog_json["title_image"]


        #stub = create_stub()

        print("DAAATAAAAA")
        pprint(data)

        note = cls.objects.create(
            stub = stub,
            local_actor = actor, 
            data = data,
            public = to is None,
            in_reply_to = in_reply_to,
            post_type = data.get("type","Note")
        )
        if to is not None:
            note.to.set(to)
        if title_image:
            attachment = Attachment(owner=actor, 
                                    note=note, 
                                    image=title_image,
                                    description=title_image.description,
                                    focus_x = title_image.focus_x,
                                    focus_y = title_image.focus_y)
            attachment.save()
            print(f"attachment url: {attachment.image_url()}")
            note.data["attachment"] = [attachment.mastodon_attachment()]
            note.save()

        return note

    @activitystreams.with_context()
    def note_json(self):
        data = self.data.copy()
        
        if self.local_actor:
            data.update({
                'published': activitystreams.format_datetime(self.published_date),
                'attributedTo': self.actor.get_absolute_url(),
                'id': self.get_stub_url(),
                'type': 'Note',
                'to': [activitystreams.PUBLIC] if self.public else [r.get_absolute_url() for r in self.to.all()]
            })
            if self.in_reply_to:
                stub = self.in_reply_to.stub
                data['inReplyTo'] = self.in_reply_to.get_stub_url()
                
            replies = self.replies.all()
            reply_items = []
            for r in replies:
                reply_items.append({
                        "type": "Note",
                        "content": r.content(),
                        "inReplyTo": r.in_reply_to.get_stub_url()
                })

            data["replies"] = {
                "type": "Collection",
                "totalItems": len(reply_items),
                "items": reply_items}
            
        return data

    def add_unique_id(self, message):
        return activitystreams.add_unique_id(self.actor.domain, message)

    @activitystreams.with_context([activitystreams.ACTIVITYSTREAMS_CONTEXT, activitystreams.SECURITY_CONTEXT])
    def create_message(self):
        return self.add_unique_id({
            'type': 'Create',
            'actor': self.actor.get_absolute_url(),
            'object': self.note_json(),
        })

    @activitystreams.with_context()
    def update_json(self):
        updated_time = activitystreams.format_datetime(self.updated_at)
        note_json = self.note_json()
        note_json['updated'] = updated_time
        return self.add_unique_id({
            'id': self.get_absolute_url()+f'#updates/{self.updated_at.timestamp()}',
            'type': 'Update',
            'actor': self.actor.get_absolute_url(),
            'object': note_json,
            'published': updated_time,
        })

    @activitystreams.with_context()
    def delete_json(self):
        return {
            'type': 'Delete',
            'actor': self.actor.get_absolute_url(),
            'object': {
                'id': self.get_absolute_url(),
                'type': 'Tombstone',
            }
        }
    
class Attachment(models.Model):
    uid = models.UUIDField(default = uuid.uuid4, primary_key = True)
    image = models.ImageField(upload_to="media/attachments", null=True)
    description = models.TextField(max_length=500, null=True, blank=True)
    note = models.ForeignKey(Note, on_delete=models.CASCADE, null=True, blank=True, related_name="attachment")
    owner = models.ForeignKey(LocalActor, on_delete=models.CASCADE, related_name="attachment")
    focus_x = models.FloatField(null=True, blank=True)
    focus_y = models.FloatField(null=True, blank=True)

    def image_url(self):
        return f"https://{settings.MAIN_DOMAIN}{self.image.url}"
    
    def mastodon_attachment(self):
        return {"type": "Image",
                "mediaType": "image/png",
                "url": self.image_url(),
                "name": self.description,
                "focus": {
                    "x": float(self.focus_x),
                    "y": float(self.focus_y),
                }}

@receiver(models.signals.post_save, sender=Note)
def note_delete_activity(sender, instance, created, **kwargs):
    note = instance
    if not created:
        note.actor.send_to_followers(note.update_json())

@receiver(models.signals.pre_delete, sender=Note)
def note_delete_activity(sender, instance, **kwargs):
    note = instance
    try:
        note.actor.send_to_followers(note.delete_json())
    except:
        pass
