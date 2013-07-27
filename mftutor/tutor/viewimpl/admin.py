# encoding: utf-8
from django import forms
from django.views.generic import FormView
from django.forms.formsets import formset_factory, BaseFormSet
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from ...settings import YEAR
from ..models import Tutor, TutorGroup, TutorProfile, RusClass

def classy(cl, size=10):
    return forms.TextInput(attrs={'class':cl, 'size':size})

class TutorForm(forms.Form):
    pk = forms.IntegerField(widget=forms.HiddenInput, required=False, label='')
    name = forms.CharField(label='Navn', required=False, widget=classy('name'))
    studentnumber = forms.CharField(label='Årskort', widget=classy('studentnumber', 7))
    study = forms.CharField(label='Studium', widget=classy('study', 7))
    email = forms.EmailField(label='Email', required=False, widget=classy('email', 25))
    rusclass = forms.ModelChoiceField(label='Rushold', queryset=RusClass.objects.filter(year__exact=YEAR), required=False)
    groups = forms.ModelMultipleChoiceField(label='Grupper', queryset=TutorGroup.objects.filter(visible=True), required=False)

    def clean_pk(self):
        data = self.cleaned_data['pk']
        if data is not None:
            t = Tutor.objects.filter(pk=data, year=YEAR)
            if t.count == 0:
                raise forms.ValidationError('Tutor med dette interne ID findes ikke.')
        return data

TutorFormSet = formset_factory(TutorForm, extra=50)

class TutorAdminView(FormView):
    form_class = TutorFormSet
    template_name = 'tutoradmin.html'

    def get_initial_for_tutor(self, tutor):
        profile = tutor.profile

        name = profile.name
        studentnumber = profile.studentnumber
        study = profile.study
        email = profile.email
        rusclass = tutor.rusclass
        groups = tutor.groups.filter(visible=True)

        return {
            'pk': tutor.pk,
            'name': name,
            'studentnumber': studentnumber,
            'study': study,
            'email': email,
            'rusclass': rusclass,
            'groups': groups,
        }

    def get_initial(self):
        tutors = Tutor.objects.filter(year=YEAR).select_related('profile')
        result = []
        for tutor in tutors:
            result.append(self.get_initial_for_tutor(tutor))

        return result

    def get_success_url(self):
        return reverse('tutor_admin')

    def form_valid(self, formset):
        changes = []

        cleaned_data = formset.cleaned_data

        for data in formset.cleaned_data:
            if data == {}:
                continue

            in_name = data['name']
            in_studentnumber = data['studentnumber']
            in_study = data['study']
            in_email = data['email']
            in_rusclass = data['rusclass']
            in_groups = data['groups']

            in_data = {
                'name': in_name,
                'studentnumber': in_studentnumber,
                'study': in_study,
                'email': in_email,
                'rusclass': in_rusclass,
                'groups': in_groups,
            }

            profile = None
            if data['pk'] is None:
                try:
                    profile = TutorProfile.objects.get(studentnumber__exact=in_studentnumber)
                    tutor = Tutor.objects.get(year=YEAR, profile=profile)
                except TutorProfile.DoesNotExist:
                    profile = TutorProfile(studentnumber=in_studentnumber)
                    profile.save()
                    tutor = Tutor(year=YEAR, profile=profile)
                except Tutor.DoesNotExist:
                    tutor = Tutor(year=YEAR, profile=profile)
                tutor.save()
                prev_data = self.get_initial_for_tutor(tutor)
                if not in_name: data['name'] = in_name = prev_data['name']
                if not in_email: data['email'] = in_email = prev_data['email']
                if not in_study: data['study'] = in_study = prev_data['study']
                if not in_rusclass: data['rusclass'] = in_rusclass = prev_data['rusclass']
                if not in_groups: data['groups'] = in_groups = prev_data['groups']

            else:
                tutor = Tutor.objects.select_related().get(pk=data['pk'], year=YEAR)
                profile = tutor.profile

                prev_data = self.get_initial_for_tutor(tutor)

                if in_data == prev_data:
                    continue

            if in_name != prev_data['name']:
                profile.name = in_name
                changes.append(u"%s: Navn ændret fra %s til %s"
                    % (unicode(tutor), unicode(prev_data['name']), unicode(in_name)))
                if ' ' in in_name:
                    first_name, last_name = in_name.split(' ', 1)
                    profile.user.first_name = first_name
                    profile.user.last_name = last_name
                else:
                    profile.user.first_name = name
                    profile.user.last_name = ''
                profile.user.save()

            if in_email != prev_data['email']:
                profile.email = in_email
                changes.append(u"%s: Email ændret fra %s til %s"
                    % (unicode(tutor), unicode(prev_data['email']), unicode(in_email)))
                profile.user.email = in_email
                profile.user.save()

            if in_studentnumber != profile.studentnumber:
                changes.append(u"%s: Årskort ændret fra %s til %s"
                    % (unicode(tutor), unicode(profile.studentnumber), unicode(in_studentnumber)))
                profile.studentnumber = in_studentnumber

            if in_study != profile.study:
                changes.append(u"%s: Studium ændret fra %s til %s"
                    % (unicode(tutor), unicode(profile.study), unicode(in_study)))
                profile.study = in_study

            if in_rusclass != tutor.rusclass:
                changes.append(u"%s: Rushold ændret fra %s til %s"
                    % (unicode(tutor), unicode(tutor.rusclass), unicode(in_rusclass)))
                tutor.rusclass = in_rusclass

            in_groupset = frozenset(g.handle for g in in_data['groups'])
            prev_groupset = frozenset(g.handle for g in prev_data['groups'])
            groups_insert = in_groupset - prev_groupset
            groups_remove = prev_groupset - in_groupset
            if data['pk'] is None:
                groups_remove = []  # don't remove existing groups if entry is new

            for handle in groups_insert:
                changes.append(u"%s tilføj gruppe %s" % (unicode(tutor), handle))
                tutor.groups.add(TutorGroup.objects.get(handle=handle))

            for handle in groups_remove:
                changes.append(u"%s fjern gruppe %s" % (unicode(tutor), handle))
                tutor.groups.remove(TutorGroup.objects.get(handle=handle))

            profile.save()
            tutor.save()

        # Here, we throw away the formset and instead get a fresh form
        formset = TutorFormSet(initial=self.get_initial())
        ctxt = self.get_context_data(form=formset, changes=changes)

        return self.render_to_response(ctxt)

    def form_invalid(self, formset):
        return self.render_to_response(self.get_context_data(form=formset))
