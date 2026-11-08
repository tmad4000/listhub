"""Tab titles and anonymous link previews name the open item without leaking private content."""
import re
import unittest

from test_ideaflow_auth import app, get_db


def meta(html, attr, name):
    match = re.search(r'<meta %s="%s" content="([^"]*)">' % (attr, re.escape(name)), html)
    return match and match.group(1)


class LinkPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        anonymous = app.test_client()
        registered = anonymous.post('/api/v1/auth/register', json={
            'username': 'previewer', 'password': 'test-password-only', 'email': 'previewer@example.test'})
        assert registered.status_code == 201, registered.data
        headers = {'Authorization': 'Bearer ' + registered.json['key']}

        def create(title, content, visibility):
            response = anonymous.post('/api/v1/items/new', headers=headers, json={
                'title': title, 'content': content, 'visibility': visibility})
            assert response.status_code == 201, response.data
            return response.json['slug']

        cls.public_slug = create('Camping "trip" checklist',
                                 '# Gear\n\n- Tent & stakes\n- Stove\n\n<!-- private -->Secret campsite code 4242<!-- /private -->',
                                 'public')
        cls.private_slug = create('Private diary', 'Very private thoughts', 'private')

    def test_public_item_preview_names_item_and_strips_private_blocks(self):
        html = app.test_client().get('/@previewer/' + self.public_slug,
                                     headers={'User-Agent': 'Twitterbot/1.0'}).get_data(as_text=True)
        self.assertIn('<title>Camping &#34;trip&#34; checklist — @previewer — ListHub</title>', html)
        self.assertEqual(meta(html, 'property', 'og:title'), 'Camping &#34;trip&#34; checklist — @previewer')
        self.assertEqual(meta(html, 'name', 'twitter:title'), 'Camping &#34;trip&#34; checklist — @previewer')
        self.assertEqual(meta(html, 'property', 'og:type'), 'article')
        self.assertEqual(meta(html, 'property', 'og:url'),
                         'https://listhub.globalbr.ai/@previewer/' + self.public_slug)
        self.assertEqual(meta(html, 'name', 'twitter:card'), 'summary')
        description = meta(html, 'property', 'og:description')
        self.assertEqual(description, 'Gear Tent &amp; stakes Stove')
        self.assertEqual(meta(html, 'name', 'description'), description)
        self.assertNotIn('4242', html)

    def test_private_item_is_not_previewable_anonymously(self):
        response = app.test_client().get('/@previewer/' + self.private_slug,
                                         headers={'User-Agent': 'facebookexternalhit/1.1'})
        self.assertEqual(response.status_code, 404)
        html = response.get_data(as_text=True)
        self.assertNotIn('Private diary', html)
        self.assertNotIn('Very private thoughts', html)

    def test_owner_tab_title_is_specific_but_description_stays_neutral(self):
        client = app.test_client()
        self.assertEqual(client.post('/login/local', data={
            'username': 'previewer', 'password': 'test-password-only'}).status_code, 302)
        html = client.get('/@previewer/' + self.private_slug).get_data(as_text=True)
        self.assertIn('<title>Private diary — @previewer — ListHub</title>', html)
        self.assertEqual(meta(html, 'property', 'og:description'), 'A list or note on ListHub.')

    def test_long_description_is_truncated_on_a_word(self):
        from views import preview_description
        item = {'visibility': 'unlisted', 'content': 'word ' * 100}
        text = preview_description(item, limit=30)
        self.assertTrue(text.endswith('…'))
        self.assertLessEqual(len(text), 31)
        self.assertEqual(preview_description({'visibility': 'shared', 'content': 'secret'}),
                         'A list or note on ListHub.')

    def test_profile_and_default_pages_have_previews(self):
        client = app.test_client()
        html = client.get('/@previewer').get_data(as_text=True)
        self.assertEqual(meta(html, 'property', 'og:title'), '@previewer — ListHub')
        self.assertEqual(meta(html, 'property', 'og:description'),
                         'Public lists and notes by @previewer on ListHub.')
        html = client.get('/community').get_data(as_text=True)
        self.assertEqual(meta(html, 'property', 'og:title'), 'Community — ListHub')


if __name__ == '__main__':
    unittest.main()
