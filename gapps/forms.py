from django import forms
from gdocsaudit import tools
from models import DomainUser
from gdata.apps.service import AppsForYourDomainException
from django.utils.safestring import mark_safe
from django.forms.widgets import RadioSelect, PasswordInput, HiddenInput
from django.http import HttpResponse, Http404, HttpResponseRedirect, HttpResponseBadRequest, HttpResponseForbidden
from django.core.urlresolvers import reverse
import logging
import re
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from gdata.client import RequestError
from gdata.apps.service import AppsForYourDomainException
from gdata.service import BadAuthentication

import gdata.apps.service
import gdata.apps.adminsettings.service

RADIO_CHOICES = [['auto', 'Distribute Documents Automatically'],
                 ['limit', 'Create a Certain Number of Documents']]

class CreateUsersForm(forms.Form):
    hidden1 = forms.CharField(label="Username", required=False, widget=HiddenInput())
    hidden2 = forms.CharField(widget=HiddenInput(), label="Password", required=False)
    hidden3 = forms.BooleanField(widget=HiddenInput(), label="Error Creating Users", required=False, initial=False)
    num_users = forms.IntegerField(label="Number of users to create", initial="10", help_text='Note: All generated users will have the default password "cl0udl0ck".')
    create_for_all = forms.BooleanField(label="Create documents for all users in the domain", required=False, initial=False)


    def __init__(self, domain, *args, **kwargs):
        super(CreateUsersForm, self).__init__(*args, **kwargs)
        self.domain = domain
        self.fields['num_users'].widget.attrs['size'] = 3


    def clean(self):
        cleaned_data = self.cleaned_data


        num_users = cleaned_data.get("num_users")
#        username = cleaned_data.get("username")
#        password = cleaned_data.get("password")
#        if num_users != 0:

#
#            try:
#                client = gdata.apps.adminsettings.service.AdminSettingsService(email='@'.join((username,self.domain)), domain=self.domain, password=password)
#                client.ProgrammaticLogin()
#                max_users = client.GetMaximumNumberOfUsers()
#            except (RequestError, AppsForYourDomainException), e:
#                #TODO have this return to a page explaining what is wrong and what the error is
#                logging.warn(e.args)
#                raise forms.ValidationError(mark_safe('We unfortunately cannot create users for this domain.  </br> <a href="%s">Click Here</a> to create users manually </br> Set Number of Users to create to 0 to continue <script type="text/javascript">$(document).ready(setupEndUser);$("#create_users_dialog").dialog(\'open\');</script>' % reverse("gapps-domain-wizard-error",kwargs=dict(domain=self.domain))))
#                #return HttpResponseRedirect(reverse("gapps-domain-wizard-error",
#                #                                   kwargs=dict(domain=self.domain)))
#
#            except BadAuthentication, e:
#                #TODO need to return this person to the page with a warning about bad username/password
#                raise forms.ValidationError(mark_safe('The username or password you entered is invalid.<script type="text/javascript">$(document).ready(setupEndUser);$("#create_users_dialog").dialog(\'open\');</script>'))

        return cleaned_data


class CreateDocsForm(forms.Form):

    #runtolimit = forms.ChoiceField(label="Auto Populate Documents", initial=True, required=False, help_text="Auto populate documents based on distribution settings in options tab.")
    #runtolimit = forms.ChoiceField(required=True, choices=RADIO_CHOICES, initial="auto", widget=RadioSelect())
    userlimit = forms.IntegerField(label="Number of documents to create", initial="500")

    shareexternal = forms.BooleanField(label="Share with external users", initial=True, help_text="Go to the options tab for additional settings for external users.", required=False)

#    def __init__(self, *args, **kwargs):
#        super(CreateDocsForm, self).__init__(*args, **kwargs)
#        self.fields['userlimit'].widget.attrs['size'] = 5
#        self.runtolimit_choice = re.findall(r'<li>(.+?)</li>',
#                                        unicode(self['runtolimit']))

class NumDocSettingsForm(forms.Form):



    #Num Docs percentages
    numdocs300to125 = forms.IntegerField(label="300 to 125", initial="2", min_value=0, max_value=100)
    numdocs125to75 = forms.IntegerField(label="125 to 75", initial="3", min_value=0, max_value=100)
    numdocs75to25 = forms.IntegerField(label="75 to 25", initial="20", min_value=0, max_value=100)
    numdocs25to10 = forms.IntegerField(label="25 to 10", initial="30", min_value=0, max_value=100)
    numdocs10to5 = forms.IntegerField(label="10 to 5", initial="40", min_value=0, max_value=100)
    numdocs5to1 = forms.IntegerField(label="5 to 1", initial="5", min_value=0, max_value=100)


    def __init__(self, domain, *args, **kwargs):
        super(NumDocSettingsForm, self).__init__(*args, **kwargs)
        self.domain = domain

        self.fields['numdocs300to125'].widget.attrs['size'] = 3
        self.fields['numdocs125to75'].widget.attrs['size'] = 3
        self.fields['numdocs75to25'].widget.attrs['size'] = 3
        self.fields['numdocs25to10'].widget.attrs['size'] = 3
        self.fields['numdocs10to5'].widget.attrs['size'] = 3
        self.fields['numdocs5to1'].widget.attrs['size'] = 3


    def clean(self):
        cleaned_data = self.cleaned_data

        numdocs300to125 = cleaned_data.get("numdocs300to125")
        numdocs125to75 = cleaned_data.get("numdocs125to75")
        numdocs75to25 = cleaned_data.get("numdocs75to25")
        numdocs25to10 = cleaned_data.get("numdocs25to10")
        numdocs10to5 = cleaned_data.get("numdocs10to5")
        numdocs5to1 = cleaned_data.get("numdocs5to1")

        numdocs = [numdocs300to125, numdocs125to75, numdocs75to25, numdocs25to10, numdocs10to5, numdocs5to1]
        if None not in numdocs:
            numdocstotal = sum(numdocs)
            if numdocstotal != 100:
                raise forms.ValidationError("Number of Documents percentages must add up to 100%")


        return  cleaned_data


class InternalShareSettingsForm(forms.Form):

    #Share percentages

    shares20to22 = forms.IntegerField(label="20 to 22", initial="1", min_value=0, max_value=100)
    shares15to20 = forms.IntegerField(label="15 to 20", initial="1", min_value=0, max_value=100)
    shares10to15 = forms.IntegerField(label="10 to 15", initial="5", min_value=0, max_value=100)
    shares5to10 = forms.IntegerField(label="5 to 10", initial="15", min_value=0, max_value=100)
    shares3to5 = forms.IntegerField(label="3 to 5", initial="20", min_value=0, max_value=100)
    shares1to3 = forms.IntegerField(label="1 to 3", initial="20", min_value=0, max_value=100)
    shares0 = forms.IntegerField(label="Not Shared", initial="38", min_value=0, max_value=100)


    def __init__(self, domain, *args, **kwargs):
        super(InternalShareSettingsForm, self).__init__(*args, **kwargs)
        self.domain = domain
        self.fields['shares20to22'].widget.attrs['size'] = 3
        self.fields['shares15to20'].widget.attrs['size'] = 3
        self.fields['shares10to15'].widget.attrs['size'] = 3
        self.fields['shares5to10'].widget.attrs['size'] = 3
        self.fields['shares3to5'].widget.attrs['size'] = 3
        self.fields['shares1to3'].widget.attrs['size'] = 3
        self.fields['shares0'].widget.attrs['size'] = 3



    def clean(self):
        cleaned_data = self.cleaned_data


        shares20to22 = cleaned_data.get("shares20to22")
        shares15to20 = cleaned_data.get("shares15to20")
        shares10to15 = cleaned_data.get("shares10to15")
        shares5to10 = cleaned_data.get("shares5to10")
        shares3to5 = cleaned_data.get("shares3to5")
        shares1to3 = cleaned_data.get("shares1to3")
        shares0 = cleaned_data.get("shares0")

        shares = [shares20to22, shares15to20, shares10to15, shares5to10, shares3to5, shares1to3, shares0]
        if None not in shares:
            sharestotal = sum(shares)
            if sharestotal != 100:
                raise forms.ValidationError("Shares percentages must add up to 100%")


        return  cleaned_data

class ExternalShareSettingsForm(forms.Form):

    sharespublic = forms.IntegerField(label="Public", initial="1", min_value=0, max_value=100)
    sharesdomain = forms.IntegerField(label="Domain", initial="1", min_value=0, max_value=100)
    sharesoutside1 = forms.IntegerField(label="Outside user 1", initial="10", min_value=0, max_value=100, required=False)
    sharesoutside2 = forms.IntegerField(label="Outside user 2", initial="10", min_value=0, max_value=100, required=False)



    def __init__(self, domain, *args, **kwargs):
        super(ExternalShareSettingsForm, self).__init__(*args, **kwargs)
        self.domain = domain

        self.fields['sharespublic'].widget.attrs['size'] = 3
        self.fields['sharesdomain'].widget.attrs['size'] = 3
        self.fields['sharesoutside1'].widget.attrs['size'] = 3
        self.fields['sharesoutside2'].widget.attrs['size'] = 3

    def _clean_outside_users(self, field):
        data = self.cleaned_data[field]
        if data:
            domain = data.split('@')[1]
            if domain == self.domain:
                raise forms.ValidationError("The external user must be from a different domain")
        return data


    def clean(self):
        cleaned_data = self.cleaned_data

        sharespublic = cleaned_data.get("sharespublic")
        sharesdomain = cleaned_data.get("sharesdomain")

        othersharestotal = sharespublic + sharesdomain
        if othersharestotal > 100:
            raise forms.ValidationError("Public and Domain share percentages must be less than 100%")

        return  cleaned_data


class ExternalUsersForm(forms.Form):

    #Outside users
    outsideuser1 = forms.EmailField(label="Outside User 1", initial="john.smith@externaluser1.com", required=False)
    outsideuser2 = forms.EmailField(label="Outside User 2", initial="externalcloudlockuser2@gmail.com", required=False)

    def __init__(self, domain, *args, **kwargs):
        super(ExternalUsersForm, self).__init__(*args, **kwargs)
        self.domain = domain


    def _clean_outside_users(self, field):
        data = self.cleaned_data[field]
        if data:
            domain = data.split('@')[1]
            if domain == self.domain:
                raise forms.ValidationError("The external user must be from a different domain")
        return data

    def clean_outsideuser1(self):
        return self._clean_outside_users("outsideuser1")

    def clean_outsideuser2(self):
        return self._clean_outside_users("outsideuser2")


    def clean(self):
        cleaned_data = self.cleaned_data

        return  cleaned_data

class DocTypeSettingsForm(forms.Form):

    #Doc Type percentages
    docratio = forms.IntegerField(label="Documents", initial="53", min_value=0, max_value=100)
    spreadratio = forms.IntegerField(label="Spreadsheets", initial="32", min_value=0, max_value=100)
    presratio = forms.IntegerField(label="Presentations", initial="3", min_value=0, max_value=100)
    pdfratio = forms.IntegerField(label="PDFs", initial="7", min_value=0, max_value=100)
    folderratio = forms.IntegerField(label="Folders", initial="5", min_value=0, max_value=100)

    def __init__(self, domain, *args, **kwargs):
        super(DocTypeSettingsForm, self).__init__(*args, **kwargs)
        self.domain = domain

        self.fields['docratio'].widget.attrs['size'] = 3
        self.fields['spreadratio'].widget.attrs['size'] = 3
        self.fields['presratio'].widget.attrs['size'] = 3
        self.fields['pdfratio'].widget.attrs['size'] = 3
        self.fields['folderratio'].widget.attrs['size'] = 3



    def clean(self):
        cleaned_data = self.cleaned_data

        docratio = cleaned_data.get("docratio")
        spreadratio = cleaned_data.get("spreadratio")
        presratio = cleaned_data.get("presratio")
        pdfratio = cleaned_data.get("pdfratio")
        folderratio = cleaned_data.get("folderratio")

        ratios = [docratio, spreadratio, presratio, pdfratio, folderratio]
        if None not in ratios:
            ratiototal = sum(ratios)
            if ratiototal != 100:
                raise forms.ValidationError("Document Type Ratios must add up to 100%")

        return  cleaned_data