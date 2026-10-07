export interface AuthIdentity {
  learner_id: string;
  user_id: string | null;
  provider: string | null;
}

export interface AuthCredentials {
  username: string;
  password: string;
}
