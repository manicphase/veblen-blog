from pprint import pprint
from   .absolute_url import absolute_reverse
from   .inbox import InboxException, get_inbox_handlers
from   .models import Attachment, LocalActor, RemoteActor, Note
from   django.conf import settings
from   django.core.exceptions import PermissionDenied
from   django.core.paginator import Paginator
from   django.views.decorators.csrf import csrf_exempt
from   django.http import HttpResponse, JsonResponse, HttpResponseBadRequest, HttpResponseNotFound
from   django.shortcuts import render, redirect
from   django.utils.decorators import method_decorator
from   django.views import View
from django.contrib.auth.models import User

import json
import re
from uuid import UUID

# Create your views here.

def index(request):
    notes = Note.objects.filter(post_type="Article").exclude(local_actor__isnull=True)
    return render(request, 'Blog/index.html', {'notes': notes})

def create_blog(request):
    if request.method == "GET":
        return render(request, "Blog/create_blog.html")
    elif request.method == "POST":
        print(request.FILES)
        title_image = request.FILES.get("title_image_upload")
        print(title_image)
        user = User.objects.get(username=request.session["user"])
        actor = user.activitypub_account.get()
        note = {k:v for k, v in request.POST.items() if k in ["title","summary","body"]}
        try:
            note["title_image"] = request.FILES.get("title_image_upload")
            note["title_image"].description = request.POST.get("title_image_description", "")
            note["title_image"].focus_x = request.POST.get("focus_x")
            note["title_image"].focus_y = request.POST.get("focus_y")

        except:
            pass
        print("NOOOOOOOOOOTE")
        pprint(note["title_image"].__dict__)
        #pprint(request.POST)
        response = actor.create_note(note)
        return redirect(response.get_stub_url())
    
def post_comment(request):
    user = User.objects.get(username=request.session["user"])
    actor = user.activitypub_account.get()
    target_comment = Note.objects.get(uid=request.POST["comment_id"])
    actor.create_note(None, content=request.POST["content"], in_reply_to=target_comment)
    return redirect(request.META["HTTP_REFERER"]) # TODO: check if this is too jank

def guidview(request):
    return HttpResponse('OK?')

def webfinger(request):
    resource = request.GET.get('resource')
    m = re.match(r'^acct:(?P<username>.+?)@(?P<domain>.+)$', resource)
    username = m.group('username')
    domain = m.group('domain')
    try:
        actor = LocalActor.objects.get(username = username, domain = domain)
    except LocalActor.DoesNotExist:
        return HttpResponseNotFound('')
    data = {
        "subject": f"acct:{actor.username}@{actor.domain}",
        "links": [
            {
                "rel": "self",
                "type": "application/activity+json",
                "href": actor.get_absolute_url(),
            }
        ]
    }
    return JsonResponse(data, content_type='application/jrd+json')

class CSRFExemptMixin:
    @csrf_exempt
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args,**kwargs)

class RequireTokenMixin:
    """
        Request must include a token in the Authorization header, or a POST or GET parameter.
    """

    def get_given_token(self):
        """
            Get the token from the request.
        """
        authorization_header = self.request.headers.get('Authorization')
        if authorization_header:
            m = re.match('Bearer (?P<token>.*)', authorization_header)
            if m:
                return m.group('token')

        return self.request.POST.get('token', self.request.GET.get('token'))

    def validate_token(self, given_token):
        """
            Validate the given token: raise a PermissionDenied exception if it is not valid.
        """
        if not self.get_actor().access_tokens.filter(access_token = given_token).exists():
            header = self.request.headers.keys()
            raise PermissionDenied(f"{given_token} is invalid {header}")


    def dispatch(self, request, *args, **kwargs):
        self.validate_token(self.get_given_token())

        return super().dispatch(request, *args, **kwargs)

class ActorView(View):
    def get_actor(self):
        username = self.kwargs['username']
        print(f"getting user {username}")
        try:
            return LocalActor.objects.get(username = username, domain = self.request.get_host())
        except:
            print(f"can't find user '{username}'")

class ProfileView(ActorView):
    def get_template_names(self):
        actor = self.get_actor()

        return [
            f'by_domain/{actor.domain}/by_user/{actor.username}/profile.html',
            f'by_domain/{actor.domain}/profile.html',
            'Blog/profile.html',
        ]

    def get(self, request, *args, **kwargs):
        actor = self.get_actor()

        paginator = Paginator(actor.notes.all(), 5)

        page_number = request.GET.get('page')
        page = paginator.get_page(page_number)

        if self.request.accepts('text/html'):
            return render(self.request, self.get_template_names(), {'actor': actor, 'profile': actor.actor_json(), 'page': page,})
        else:
            print(actor.__dict__)
            return JsonResponse(actor.actor_json(), content_type='application/activity+json')

class UpdateProfileView(ActorView):
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        from . import tasks

        actor = self.get_actor()
        tasks.update_profile(actor)
        
        return redirect(actor.get_absolute_url())

class FollowersView(ActorView):
    def get(self, request, *args, **kwargs):
        actor = self.get_actor()
        json = actor.followers_json()
        return JsonResponse(json)

class InboxView(CSRFExemptMixin, ActorView):
    def post(self, request, *args, **kwargs):
        activity = json.load(request)
        print("ACTIVITY")
        pprint(activity)

        actor = self.get_actor()
        inbox_handlers = get_inbox_handlers(actor, activity)

        result = None

        for inbox_handler in inbox_handlers:
            try:
                print(inbox_handler,"handling")
                hresult = inbox_handler.handle(activity)
                print("Activity result:",result)
                if hresult is not None:
                    result = hresult

            except InboxException as e:
                print("Inbox error: ",e)

        if result is not None:
            return JsonResponse(result)
        else:
            return HttpResponse('')

class OutboxView(ActorView):
    def get(self, request, *args, **kwargs):
        actor = self.get_actor()
        json = actor.outbox_json()
        return JsonResponse(json)

class NoteView(ActorView):
    def get_note(self):
        uid = self.kwargs.get('uid')
        try:
            UUID(uid, version=4) 
            return self.get_actor().notes.get(uid = uid)
        except:
            return self.get_actor().notes.get(stub=uid)

    def get(self, request, *args, **kwargs):
        note = self.get_note()
        print(note)
        print("KWARGS")
        pprint(self.kwargs)
        pprint(request.headers)
        if self.kwargs.get('content-type') == 'json' or "json" in request.headers.get("Accept"):
            print("return json")
            print(note.note_json())
            return JsonResponse(note.note_json(), content_type='application/activity+json')
        else:
            return render(self.request, 'Blog/note.html', {'note': note})

class CreateNoteView(CSRFExemptMixin, RequireTokenMixin, ActorView):
    def post(self, request, *args, **kwargs):
        content = request.POST['content']
        print(content)
        note = self.get_actor().create_note(content)
        return redirect(note.get_absolute_url())
