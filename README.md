# veblen-blog
Django app. Activitypub enabled blog

This django app is based on [christianp's django activitypu bot](https://github.com/christianp/django-activitypub-bot) 


To install this app, make the following changes to the following files in your main Django site folder -

## settings.py

add `"Blog.apps.BlogConfig"` to `INSTALLED_APPS`

add the line `ACTORS_DIR = 'actors'`
add the line `SCHEME = 'https'`

seperate out live domains into a list named `DOMAINS`, and make `ALLOWED_HOSTS` a list which concatenates test domains with `DOMAINS`

```python
DOMAINS = [
    'publicslate.co.uk',
    'ppl.manicphase.me',
]

ALLOWED_HOSTS = DOMAINS + [
    'localhost'
]
```

## urls.py

add 
```python

from django.conf import settings
from Blog.views import webfinger

urlpatterns += [
    path('account/', include('Blog.urls')),
]

urlpatterns += [
    path('.well-known/webfinger', webfinger),
    path('blog/', include("Blog.urls"))
]

```

# Using the blog
* this bit is subject to change a lot as the software is actually developed. As of now it's just been made into a state where it runs *

## Make an account
Use the command `python manage.py create_actor` and follow the instructions.

## Make a post
Create a super user if you haven't done so already.
With the server running, go to https://{your domain}/admin and log in.
Navigate to BLOG > Local actors using the menu on the left.
Click the "create a note" link at the bottom of the page.