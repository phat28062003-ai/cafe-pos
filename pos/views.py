from django.shortcuts import render


def index(request):
    """Giao diện Cafe POS & Barista KDS Dashboard"""
    return render(request, "index.html")
