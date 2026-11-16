import os, tempfile, unittest
from app import app, init_db, get_db
from werkzeug.security import generate_password_hash
class FeedbackHubTest(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(); app.config.update(TESTING=True,DATABASE=os.path.join(self.temp.name,'test.sqlite3'),SECRET_KEY='test-secret'); self.client=app.test_client()
  with app.app_context():
   init_db(); get_db().execute('INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,?)',('Admin','admin@test.local',generate_password_hash('password123456'),'admin')); get_db().commit()
 def tearDown(self): self.temp.cleanup()
 def test_registration(self):
  r=self.client.post('/register',data={'name':'Student','email':'s@test.local','password':'password123'},follow_redirects=True); self.assertEqual(r.status_code,200); self.assertIn(b'Available forms',r.data)
 def test_admin_permissions(self):
  self.client.post('/register',data={'name':'Student','email':'s@test.local','password':'password123'}); self.assertEqual(self.client.get('/admin/dashboard').status_code,403)
if __name__=='__main__': unittest.main()
