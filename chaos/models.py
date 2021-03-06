# encoding: utf-8

# Copyright (c) 2001-2014, Canal TP and/or its affiliates. All rights reserved.
#
# This file is part of Navitia,
#     the software to build cool stuff with public transport.
#
# Hope you'll enjoy and contribute to this project,
#     powered by Canal TP (www.canaltp.fr).
# Help us simplify mobility and open public transport:
#     a non ending quest to the responsive locomotion way of traveling!
#
# LICENCE: This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
# Stay tuned using
# twitter @navitia
# IRC #navitia on freenode
# https://groups.google.com/d/forum/navitia
# www.navitia.io

import uuid
from chaos import db, utils, exceptions
from utils import paginate, get_current_time
from sqlalchemy.dialects.postgresql import UUID, BIT
from datetime import datetime
from formats import publication_status_values
from sqlalchemy import or_, and_, between
from sqlalchemy.orm import aliased


# force the server to use UTC time for each connection
import sqlalchemy


def set_utc_on_connect(dbapi_con, con_record):
    c = dbapi_con.cursor()
    c.execute("SET timezone='utc'")
    c.close()
sqlalchemy.event.listen(sqlalchemy.pool.Pool, 'connect', set_utc_on_connect)


class TimestampMixin(object):
    created_at = db.Column(
        db.DateTime(),
        default=datetime.utcnow,
        nullable=False
    )
    updated_at = db.Column(
        db.DateTime(),
        default=None,
        onupdate=datetime.utcnow
    )

DisruptionStatus = db.Enum(
    'published',
    'archived',
    'draft',
    name='disruption_status'
)

SeverityEffect = db.Enum(
    'no_service',
    'reduced_service',
    'significant_delays',
    'detour',
    'additional_service',
    'modified_service',
    'other_effect',
    'unknown_effect',
    'stop_moved',
    name='severity_effect'
)

ImpactStatus = db.Enum('published', 'archived', name='impact_status')

PtObjectType = db.Enum(
    'network',
    'stop_area',
    'line',
    'line_section',
    'route',
    'stop_point',
    name='pt_object_type'
)

ChannelTypeEnum = db.Enum(
    'web',
    'sms',
    'email',
    'mobile',
    'notification',
    'twitter',
    'facebook'
)


class Client(TimestampMixin, db.Model):
    __tablename__ = 'client'
    id = db.Column(UUID, primary_key=True)
    client_code = db.Column(db.Text, unique=True, nullable=False)

    def __init__(self, code=None):
        self.id = str(uuid.uuid1())
        self.client_code = code

    @classmethod
    def get_by_code(cls, code):
        return cls.query.filter_by(client_code=code).first()

    @classmethod
    def get_or_create(cls, code):
        client = cls.query.filter_by(client_code=code).first()
        if not client:
            client = Client(code)
        return client


class Contributor(TimestampMixin, db.Model):
    __tablename__ = 'contributor'
    id = db.Column(UUID, primary_key=True)
    contributor_code = db.Column(db.Text, unique=True, nullable=False)

    def __init__(self, code=None):
        self.id = str(uuid.uuid1())
        self.contributor_code = code

    @classmethod
    def get_by_code(cls, code):
        return cls.query.filter_by(contributor_code=code).first()

    @classmethod
    def get_or_create(cls, code):
        contributor = cls.query.filter_by(contributor_code=code).first()
        if not contributor:
            contributor = Contributor(code)
        return contributor


associate_wording_severity = db.Table(
    'associate_wording_severity',
    db.metadata,
    db.Column('wording_id', UUID, db.ForeignKey('wording.id')),
    db.Column('severity_id', UUID, db.ForeignKey('severity.id')),
    db.PrimaryKeyConstraint(
        'wording_id',
        'severity_id',
        name='wording_severity_pk'
    )
)


class Severity(TimestampMixin, db.Model):
    """
    represent the severity of an impact
    """
    id = db.Column(UUID, primary_key=True)
    wording = db.Column(db.Text, unique=False, nullable=False)
    color = db.Column(db.Text, unique=False, nullable=True)
    is_visible = db.Column(
        db.Boolean, unique=False, nullable=False, default=True
    )
    priority = db.Column(db.Integer, unique=False, nullable=True)
    effect = db.Column(SeverityEffect, nullable=True)
    client_id = db.Column(UUID, db.ForeignKey(Client.id), nullable=False)
    client = db.relationship('Client', backref='severity', lazy='joined')
    wordings = db.relationship(
        "Wording", secondary=associate_wording_severity, backref="severities"
    )

    def delete_wordings(self):
        index = len(self.wordings) - 1
        while index >= 0:
            wording = self.wordings[index]
            self.wordings.remove(wording)
            db.session.delete(wording)
            index -= 1

    def __init__(self):
        self.id = str(uuid.uuid1())
        self.effect = 'unknown_effect'

    def __repr__(self):
        return '<Severity %r>' % self.id

    @classmethod
    def all(cls, client_id):
        return cls.query.filter_by(
            client_id=client_id,
            is_visible=True
        ).order_by(cls.priority).all()

    @classmethod
    def get(cls, id, client_id):
        severity = cls.query.filter_by(
                id=id,
                client_id=client_id,
                is_visible=True
            ).first()

        if severity is None:
            raise exceptions.ObjectUnknown('The severty with id {} does not exist for this client'.format(id))

        return severity

class Category(TimestampMixin, db.Model):
    """
    represent the category of a cause
    """
    __tablename__ = 'category'
    id = db.Column(UUID, primary_key=True)
    name = db.Column(db.Text, unique=False, nullable=False)
    is_visible = db.Column(
        db.Boolean, unique=False, nullable=False, default=True
    )
    client_id = db.Column(UUID, db.ForeignKey(Client.id), nullable=False)
    client = db.relationship('Client', backref='categories', lazy='joined')
    __table_args__ = (db.UniqueConstraint(
        'name', 'client_id', name='category_name_client_id_key'
    ),)

    def __init__(self):
        self.id = str(uuid.uuid1())

    def __repr__(self):
        return '<Category %r>' % self.id

    @classmethod
    def all(cls, client_id):
        return cls.query.filter_by(
            client_id=client_id,
            is_visible=True
        ).order_by(cls.name).all()

    @classmethod
    def get(cls, id, client_id):
        return cls.query.filter_by(
            id=id,
            client_id=client_id,
            is_visible=True
        ).first_or_404()

    @classmethod
    def get_archived_by_name(cls, name, client_id):
        return cls.query.filter_by(
            name=name,
            client_id=client_id,
            is_visible=False
        ).first()


class Wording(TimestampMixin, db.Model):
    """
    represent the Wording of a cause
    """
    id = db.Column(UUID, primary_key=True)
    key = db.Column(db.Text, unique=False, nullable=False)
    value = db.Column(db.Text, unique=False, nullable=False)

    def __init__(self):
        self.id = str(uuid.uuid1())

    def __repr__(self):
        return '<Wording %r>' % self.id

associate_wording_cause = db.Table(
    'associate_wording_cause',
    db.metadata,
    db.Column('wording_id', UUID, db.ForeignKey('wording.id')),
    db.Column('cause_id', UUID, db.ForeignKey('cause.id')),
    db.PrimaryKeyConstraint('wording_id', 'cause_id', name='wording_cause_pk')
)


class Cause(TimestampMixin, db.Model):
    """
    represent the cause of a disruption
    """
    id = db.Column(UUID, primary_key=True)
    # TODO A supprimer plus tard
    wording = db.Column(db.Text, unique=False, nullable=False)
    is_visible = db.Column(db.Boolean, unique=False, nullable=False, default=True)
    client_id = db.Column(UUID, db.ForeignKey(Client.id), nullable=False)
    client = db.relationship('Client', backref='causes', lazy='joined')
    category_id = db.Column(UUID, db.ForeignKey(Category.id), nullable=True)
    category = db.relationship('Category', backref='causes', lazy='joined')
    wordings = db.relationship("Wording", secondary=associate_wording_cause, backref="causes")

    def __init__(self):
        self.id = str(uuid.uuid1())

    def __repr__(self):
        return '<Cause %r>' % self.id

    @classmethod
    def all(cls, client_id, category_id=None):
        kargs = {"client_id": client_id,
                 "is_visible": True}
        if category_id:
            kargs["category_id"] = category_id
        return cls.query.filter_by(**kargs).all()

    @classmethod
    def get(cls, id, client_id, category_id=None):
        kargs = {"client_id": client_id,
                 "is_visible": True,
                 "id": id}
        if category_id:
            kargs["category_id"] = category_id
        return cls.query.filter_by(**kargs).first_or_404()

    def delete_wordings(self):
        index = len(self.wordings) - 1
        while index >= 0:
            wording = self.wordings[index]
            self.wordings.remove(wording)
            db.session.delete(wording)
            index -= 1

associate_disruption_tag = db.Table(
    'associate_disruption_tag',
    db.metadata,
    db.Column('tag_id', UUID, db.ForeignKey('tag.id')),
    db.Column('disruption_id', UUID, db.ForeignKey('disruption.id')),
    db.PrimaryKeyConstraint(
        'tag_id',
        'disruption_id',
        name='tag_disruption_pk'
    )
)


class Tag(TimestampMixin, db.Model):
    """
    represent the tag of a disruption
    """
    __tablename__ = 'tag'
    id = db.Column(UUID, primary_key=True)
    name = db.Column(db.Text, unique=False, nullable=False)
    is_visible = db.Column(db.Boolean, unique=False, nullable=False, default=True)
    client_id = db.Column(UUID, db.ForeignKey(Client.id), nullable=False)
    client = db.relationship('Client', backref='tags', lazy='joined')
    __table_args__ = (db.UniqueConstraint('name', 'client_id', name='tag_name_client_id_key'),)

    def __init__(self):
        self.id = str(uuid.uuid1())

    def __repr__(self):
        return '<Tag %r>' % self.id

    @classmethod
    def all(cls, client_id):
        return cls.query.filter_by(client_id=client_id,is_visible=True).all()

    @classmethod
    def get(cls, id, client_id):
        return cls.query.filter_by(id=id, client_id=client_id, is_visible=True).first_or_404()

    @classmethod
    def get_archived_by_name(cls, name, client_id):
        return cls.query.filter_by(name=name, client_id=client_id, is_visible=False).first()


associate_disruption_pt_object = db.Table(
    'associate_disruption_pt_object',
    db.metadata,
    db.Column('disruption_id', UUID, db.ForeignKey('disruption.id')),
    db.Column('pt_object_id', UUID, db.ForeignKey('pt_object.id')),
    db.PrimaryKeyConstraint(
        'disruption_id',
        'pt_object_id',
        name='disruption_pt_object_pk'
    )
)


class AssociateDisruptionProperty(db.Model):
    """
    links disruptions to properties
    """
    __tablename__ = 'associate_disruption_property'
    value = db.Column(db.Text, primary_key=True)
    disruption_id = db.Column(
        UUID,
        db.ForeignKey('disruption.id'),
        primary_key=True
    )
    property_id = db.Column(
        UUID,
        db.ForeignKey('property.id'),
        primary_key=True
    )
    property = db.relationship('Property', back_populates='disruptions')
    disruption = db.relationship('Disruption', back_populates='properties')

    @classmethod
    def get(cls, property_id, disruption_id, value):
        return cls.query.filter_by(
            property_id=property_id,
            disruption_id=disruption_id,
            value=value
        ).first()

    @classmethod
    def get_by_disruption(cls, disruption_id):
        return cls.query.filter_by(
            disruption_id=disruption_id
        ).all()

    def __repr__(self):
        return '<%s: %s %s %s>' % (
            self.__class__.__name__,
            self.property_id,
            self.disruption_id,
            self.value
        )


class Disruption(TimestampMixin, db.Model):
    __tablename__ = 'disruption'
    id = db.Column(UUID, primary_key=True)
    reference = db.Column(db.Text, unique=False, nullable=True)
    note = db.Column(db.Text, unique=False, nullable=True)
    status = db.Column(
        DisruptionStatus, nullable=False, default='published', index=True
    )
    start_publication_date = db.Column(db.DateTime(), nullable=True)
    end_publication_date = db.Column(db.DateTime(), nullable=True)
    impacts = db.relationship('Impact', backref='disruption', lazy='joined', cascade='delete')
    cause_id = db.Column(UUID, db.ForeignKey(Cause.id))
    cause = db.relationship('Cause', backref='disruption', lazy='joined')
    tags = db.relationship("Tag", secondary=associate_disruption_tag, backref="disruptions", lazy='joined')
    client_id = db.Column(UUID, db.ForeignKey(Client.id), nullable=False)
    client = db.relationship('Client', backref='disruptions', lazy='joined')
    contributor_id = db.Column(UUID, db.ForeignKey(Contributor.id), nullable=False)
    contributor = db.relationship('Contributor', backref='disruptions', lazy='joined')
    version = db.Column(db.Integer, nullable=False, default=1)
    localizations = db.relationship("PTobject", secondary=associate_disruption_pt_object,
                                    backref="disruptions", lazy='joined')
    properties = db.relationship(
        'AssociateDisruptionProperty',
        lazy='joined',
        back_populates='disruption',
        cascade='delete'
    )

    def __repr__(self):
        return '<Disruption %r>' % self.id

    def __init__(self):
        self.id = str(uuid.uuid1())

    def upgrade_version(self):
        self.version = self.version + 1

    def archive(self):
        """
        archive the disruption, it will not be visible on any media
        """
        self.status = 'archived'
        for impact in self.impacts:
            impact.archive()

    def is_published(self):
        return self.status == 'published'

    def is_draft(self):
        return self.status == 'draft'

    @classmethod
    def get(cls, id, contributor_id):
        return cls.query.filter(
            (cls.id == id) and
            (cls.contributor == contributor_id) and
            (cls.status != 'archived')
        ).first_or_404()

    @classmethod
    @paginate()
    def all_with_filter(cls, contributor_id, publication_status, ends_after_date, ends_before_date, tags, uri, line_section, statuses):
        availlable_filters = {
            'past': and_(cls.end_publication_date != None, cls.end_publication_date < get_current_time()),
            'ongoing': and_(cls.start_publication_date <= get_current_time(),
                            or_(cls.end_publication_date == None, cls.end_publication_date >= get_current_time())),
            'coming': Disruption.start_publication_date > get_current_time()
        }
        query = cls.query.filter(and_(
            cls.contributor_id == contributor_id,
            cls.status.in_(statuses)
        ))

        if ends_after_date:
            query = query.filter(cls.end_publication_date >= ends_after_date)

        if ends_before_date:
            query = query.filter(cls.end_publication_date <= ends_before_date)

        if tags:
            query = query.filter(cls.tags.any(Tag.id.in_(tags)))

        if uri:
            query = query.join(cls.impacts)
            query = query.filter(Impact.status == 'published')
            query = query.join(Impact.objects)

            #Here add a new query to find impacts with line_section having uri as line
            if line_section :
                query_line_section = query
                query_line_section = query_line_section.filter(and_(PTobject.type == "line_section", PTobject.uri.like(uri + ":%")))

            query = query.filter(PTobject.uri == uri)

        publication_status = set(publication_status)
        if len(publication_status) == len(publication_status_values):
            #For a query by uri use union with the query for line_section
            if uri and line_section:
                query = query.union(query_line_section)

        else:
            filters = [availlable_filters[status] for status in publication_status]
            query = query.filter(or_(*filters))

            #For a query by uri use union with the query for line_section
            if uri and line_section:
                query_line_section = query_line_section.filter(or_(*filters))
                query = query.union(query_line_section)

        return query.order_by(cls.end_publication_date, cls.id)

    @property
    def publication_status(self):
        current_time = utils.get_current_time()
        # Past
        if (self.end_publication_date != None) and (self.end_publication_date < current_time):
            return "past"
        # ongoing
        if self.start_publication_date <= current_time\
            and (self.end_publication_date == None or self.end_publication_date >= current_time):
            return "ongoing"
        # Coming
        if self.start_publication_date > current_time:
            return "coming"

    @classmethod
    def traffic_report_filter(cls, contributor_id):
        query = cls.query.filter(cls.status == 'published')
        query = query.filter(cls.contributor_id == contributor_id)
        query = query.filter(
            between(get_current_time(), cls.start_publication_date, cls.end_publication_date))
        return query.all()


associate_impact_pt_object = db.Table(
    'associate_impact_pt_object',
    db.metadata,
    db.Column('impact_id', UUID, db.ForeignKey('impact.id')),
    db.Column('pt_object_id', UUID, db.ForeignKey('pt_object.id')),
    db.PrimaryKeyConstraint(
        'impact_id',
        'pt_object_id',
        name='impact_pt_object_pk'
    )
)


class Impact(TimestampMixin, db.Model):
    id = db.Column(UUID, primary_key=True)
    status = db.Column(ImpactStatus, nullable=False, default='published', index=True)
    disruption_id = db.Column(UUID, db.ForeignKey(Disruption.id))
    severity_id = db.Column(UUID, db.ForeignKey(Severity.id))
    messages = db.relationship('Message', backref='impact', lazy='joined')
    application_periods = db.relationship('ApplicationPeriods', backref='impact', lazy='joined')
    severity = db.relationship('Severity', backref='impacts', lazy='joined')
    objects = db.relationship("PTobject", secondary=associate_impact_pt_object, lazy='joined', order_by="PTobject.type, PTobject.uri")
    patterns = db.relationship('Pattern', backref='impact', lazy='joined')
    send_notifications = db.Column(db.Boolean, unique=False, nullable=False, default=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    notification_date = db.Column(db.DateTime(), default=None, nullable=True)

    def __repr__(self):
        return '<Impact %r>' % self.id

    def __marshallable__(self):
        '''
        This method is added to solve the problem of impact without instance during creation of response json for Post..
        API post cannot fill url for impact and disruption in impact_fields
        When we have either one of them present in impact_fields, it works.
        '''
        d = {}
        d['id'] = self.id
        d['status'] = self.status
        d['disruption_id'] = self.disruption_id
        d['severity_id'] = self.severity_id
        d['objects'] = self.objects
        d['application_periods'] = self.application_periods
        d['severity'] = self.severity
        d['messages'] = self.messages
        d['application_period_patterns'] = self.patterns
        d['send_notifications'] = self.send_notifications
        d['notification_date'] = self.notification_date
        return d

    def __init__(self, objects=None):
        self.id = str(uuid.uuid1())

    def archive(self):
        """
        archive the impact, it will not be visible on any media
        """
        self.status = 'archived'

    def insert_object(self, object):
        """
        Adds an objectTC in a imapct.
        """
        self.objects.append(object)
        db.session.add(object)

    def upgrade_version(self):
        self.version = self.version + 1

    def insert_message(self, message):
        """
        Adds an message in a imapct.
        """
        self.messages.append(message)
        db.session.add(message)

    def delete_message(self, message):
        """
        delete a message in an impact.
        """
        self.messages.remove(message)
        db.session.delete(message)

    def delete_app_periods(self):
        for app_per in self.application_periods:
            db.session.delete(app_per)

    def delete_line_section(self):
        for pt_object in self.objects:
            if pt_object.type == 'line_section':
                line_section = LineSection.get_by_object_id(pt_object.id)
                if line_section:
                    db.session.delete(line_section)
                self.delete(pt_object)
                db.session.delete(pt_object)


    def insert_app_period(self, application_period):
        """
        Adds an ApplicationPeriods in a impact.
        """
        self.application_periods.append(application_period)
        db.session.add(application_period)

    def delete_patterns(self):
        for i in range(len(self.patterns), 0, -1):
            pattern = self.patterns[i - 1]
            pattern.delete_time_slots()
            self.patterns.remove(pattern)
            db.session.delete(pattern)

    def insert_pattern(self, pattern):
        """
        Adds a pattern of ApplicationPeriods in a impact.
        """
        self.patterns.append(pattern)
        db.session.add(pattern)

    @classmethod
    def get(cls, id, contributor_id):
        query = cls.query.filter_by(id=id, status='published')
        query = query.join(Disruption)
        query = query.filter(Disruption.contributor_id == contributor_id)
        return query.first_or_404()

    @classmethod
    @paginate()
    def all(cls, disruption_id, contributor_id):
        alias = aliased(Severity)
        query = cls.query.filter_by(status='published')
        query = query.filter(and_(cls.disruption_id == disruption_id))
        query = query.join(Disruption)
        query = query.filter(Disruption.contributor_id == contributor_id)
        return query.join(alias, Impact.severity).order_by(alias.priority)

    @classmethod
    def all_with_filter(cls, start_date, end_date, pt_object_type, uris, contributor_id):
        pt_object_alias = aliased(PTobject)
        query = cls.query.filter(cls.status == 'published')
        query = query.join(Disruption)
        query = query.join(ApplicationPeriods)
        query = query.join(pt_object_alias, cls.objects)
        query = query.filter(Disruption.contributor_id == contributor_id)
        query = query.filter(and_(ApplicationPeriods.start_date <= end_date, ApplicationPeriods.end_date >= start_date))

        if pt_object_type or uris:
            alias_line = aliased(PTobject)
            alias_start_point = aliased(PTobject)
            alias_end_point = aliased(PTobject)
            alias_route = aliased(PTobject)
            alias_via = aliased(PTobject)

            query_line_section = query
            query_line_section = query_line_section.join(pt_object_alias.line_section)
            query_line_section = query_line_section.join(alias_line, LineSection.line_object_id == alias_line.id)
            query_line_section = query_line_section.join(alias_start_point, LineSection.start_object_id == alias_start_point.id)
            query_line_section = query_line_section.join(alias_end_point, LineSection.end_object_id == alias_end_point.id)
            query_line_section = query_line_section.join(alias_route, LineSection.routes)
            query_line_section = query_line_section.join(alias_via, LineSection.via)

        if pt_object_type:
            query = query.filter(pt_object_alias.type == pt_object_type)
            type_filters = []
            type_filters.append(alias_line.type == pt_object_type)
            type_filters.append(alias_start_point.type == pt_object_type)
            type_filters.append(alias_end_point.type == pt_object_type)
            query_line_section = query_line_section.filter(or_(*type_filters))

        if uris:
            uri_filters = []
            uri_filters.append(alias_line.uri.in_(uris))
            uri_filters.append(alias_start_point.uri.in_(uris))
            uri_filters.append(alias_end_point.uri.in_(uris))
            uri_filters.append(alias_route.uri.in_(uris))
            uri_filters.append(alias_via.uri.in_(uris))
            query_line_section = query_line_section.filter(or_(*uri_filters))
            query = query.filter(pt_object_alias.uri.in_(uris))

        start_filter = "application_periods_1.start_date <= '{end_date}'".format(end_date=end_date)
        end_filter = "application_periods_1.end_date >= '{start_date}'".format(start_date=start_date)
        query = query.union_all(query_line_section).filter(and_(start_filter, end_filter)).order_by("application_periods_1.start_date")
        return query.all()


associate_line_section_route_object = db.Table(
    'associate_line_section_route_object',
    db.metadata,
    db.Column('line_section_id', UUID, db.ForeignKey('line_section.id')),
    db.Column('route_object_id', UUID, db.ForeignKey('pt_object.id')),
    db.PrimaryKeyConstraint(
        'line_section_id',
        'route_object_id',
        name='line_section_route_object_pk'
    )
)


associate_line_section_via_object = db.Table(
    'associate_line_section_via_object',
    db.metadata,
    db.Column('line_section_id', UUID, db.ForeignKey('line_section.id')),
    db.Column('stop_area_object_id', UUID, db.ForeignKey('pt_object.id')),
    db.PrimaryKeyConstraint(
        'line_section_id',
        'stop_area_object_id',
        name='line_section_stop_area_object_pk'
    )
)


class PTobject(TimestampMixin, db.Model):
    __tablename__ = 'pt_object'
    id = db.Column(UUID, primary_key=True)
    type = db.Column(PtObjectType, nullable=False, default='network', index=True)
    uri = db.Column(db.Text, primary_key=True)
    line_section = db.relationship('LineSection',
                                   foreign_keys='LineSection.object_id',
                                   backref='pt_object',
                                   uselist=False)

    def __repr__(self):
        return '<PTobject %r>' % self.id

    def __init__(self, type=None, code=None):
        self.id = str(uuid.uuid1())
        self.type = type
        self.uri = code

    def insert_line_section(self, line_section):
        """
        Adds a line_section in an object.
        """
        self.line_section = line_section
        db.session.add(line_section)

    @classmethod
    def get(cls, id):
        return cls.query.filter_by(id=id).first_or_404()

    @classmethod
    def get_pt_object_by_uri(cls, uri):
        return cls.query.filter_by(uri=uri).first()


class ApplicationPeriods(TimestampMixin, db.Model):
    """
    represents the application periods of an impact
    """
    id = db.Column(UUID, primary_key=True)
    start_date = db.Column(db.DateTime(), nullable=True)
    end_date = db.Column(db.DateTime(), nullable=True)
    impact_id = db.Column(UUID, db.ForeignKey(Impact.id), index=True)

    def __init__(self, impact_id=None):
        self.id = str(uuid.uuid1())
        self.impact_id = impact_id

    def __repr__(self):
        return '<ApplicationPeriods %r>' % self.id


class Channel(TimestampMixin, db.Model):
    """
    represent the channel for the message of an impact
    """
    id = db.Column(UUID, primary_key=True)
    name = db.Column(db.Text, unique=False, nullable=False)
    max_size = db.Column(db.Integer, unique=False, nullable=True)
    content_type = db.Column(db.Text, unique=False, nullable=True)
    is_visible = db.Column(db.Boolean, unique=False, nullable=False, default=True)
    client_id = db.Column(UUID, db.ForeignKey(Client.id), nullable=False)
    client = db.relationship('Client', backref='channels', lazy='joined')
    channel_types = db.relationship('ChannelType', backref='channel', lazy='joined')

    def __init__(self):
        self.id = str(uuid.uuid1())

    def __repr__(self):
        return '<Channel %r>' % self.id

    def delete_channel_types(self):
        """
        Deletes a channel_type in the channel
        """
        index = len(self.channel_types) - 1
        while index >= 0:
            type = self.channel_types[index]
            self.channel_types.remove(type)
            db.session.delete(type)
            index -= 1

    def insert_channel_type(self, channel_type):
        """
        Adds a channel_type in the channel
        """
        self.channel_types.append(channel_type)
        db.session.add(channel_type)

    @classmethod
    def all(cls, client_id):
        return cls.query.filter_by(client_id=client_id, is_visible=True).order_by(cls.name). all()

    @classmethod
    def get(cls, id, client_id):
        return cls.query.filter_by(id=id, client_id=client_id, is_visible=True).first_or_404()


class Message(TimestampMixin, db.Model):
    """
    represent the message of an impact
    """
    id = db.Column(UUID, primary_key=True)
    text = db.Column(db.Text, unique=False, nullable=False)
    impact_id = db.Column(UUID, db.ForeignKey(Impact.id))
    channel_id = db.Column(UUID, db.ForeignKey(Channel.id))
    channel = db.relationship('Channel', backref='message', lazy='select')

    def __init__(self):
        self.id = str(uuid.uuid1())

    def __repr__(self):
        return '<Message %r>' % self.id

    @classmethod
    def all(cls):
        return cls.query.all()

    @classmethod
    def get(cls, id):
        return cls.query.filter_by(id=id).first_or_404()


associate_wording_line_section = db.Table(
    'associate_wording_line_section',
    db.metadata,
    db.Column('wording_id', UUID, db.ForeignKey('wording.id')),
    db.Column('line_section_id', UUID, db.ForeignKey('line_section.id')),
    db.PrimaryKeyConstraint(
        'wording_id',
        'line_section_id',
        name='wording_line_section_pk'
    )
)


class LineSection(TimestampMixin, db.Model):
    __tablename__ = 'line_section'
    id = db.Column(UUID, primary_key=True)
    line_object_id = db.Column(UUID, db.ForeignKey(PTobject.id), nullable=False)
    start_object_id = db.Column(UUID, db.ForeignKey(PTobject.id), nullable=False)
    end_object_id = db.Column(UUID, db.ForeignKey(PTobject.id), nullable=False)
    sens = db.Column(db.Integer, unique=False, nullable=True)
    object_id = db.Column(UUID, db.ForeignKey(PTobject.id))
    line = db.relationship('PTobject', foreign_keys=line_object_id)
    start_point = db.relationship('PTobject', foreign_keys=start_object_id)
    end_point = db.relationship('PTobject', foreign_keys=end_object_id)
    routes = db.relationship("PTobject", secondary=associate_line_section_route_object, lazy='joined')
    via = db.relationship("PTobject", secondary=associate_line_section_via_object, lazy='joined')
    wordings = db.relationship("Wording", secondary=associate_wording_line_section, backref="linesections")

    def delete_wordings(self):
        index = len(self.wordings) - 1
        while index >= 0:
            wording = self.wordings[index]
            self.wordings.remove(wording)
            db.session.delete(wording)
            index -= 1

    def __repr__(self):
        return '<LineSection %r>' % self.id

    def __init__(self, object_id=None):
        self.id = str(uuid.uuid1())
        self.object_id = object_id

    @classmethod
    def get(cls, id):
        return cls.query.filter_by(id=id).first_or_404()

    @classmethod
    def get_by_object_id(cls, object_id):
        return cls.query.filter_by(object_id=object_id).first()


class Pattern(TimestampMixin, db.Model):
    """
    represents the patterns of application periods of an impact
    """
    __tablename__ = 'pattern'
    id = db.Column(UUID, primary_key=True)
    start_date = db.Column(db.Date(), nullable=True)
    end_date = db.Column(db.Date(), nullable=True)
    weekly_pattern = db.Column(BIT(7), unique=False, nullable=False)
    impact_id = db.Column(UUID, db.ForeignKey(Impact.id), index=True)
    time_slots = db.relationship('TimeSlot', backref='pattern', lazy='joined')

    def __init__(self, impact_id=None):
        self.id = str(uuid.uuid1())
        self.impact_id = impact_id

    def __repr__(self):
        return '<Pattern %r>' % self.id

    def delete_time_slots(self):
        for time_slot in self.time_slots:
            db.session.delete(time_slot)

    def insert_time_slot(self, time_slot):
        """
        Adds a time slot in the pattern
        """
        self.time_slots.append(time_slot)
        db.session.add(time_slot)


class TimeSlot(TimestampMixin, db.Model):
    """
    represents the time slots of a pattern
    """
    __tablename__ = 'time_slot'
    id = db.Column(UUID, primary_key=True)
    begin = db.Column(db.Time(), nullable=True)
    end = db.Column(db.Time(), nullable=True)
    pattern_id = db.Column(UUID, db.ForeignKey(Pattern.id), index=True)

    def __init__(self, pattern_id=None):
        self.id = str(uuid.uuid1())
        self.pattern_id = pattern_id

    def __repr__(self):
        return '<TimeSlot %r>' % self.id


class ChannelType(TimestampMixin, db.Model):
    """
    represents the types of a channel
    """
    __tablename__ = 'channel_type'
    id = db.Column(UUID, primary_key=True)
    channel_id = db.Column(UUID, db.ForeignKey(Channel.id), index=True)
    name = db.Column(ChannelTypeEnum, nullable=False, default='web')

    def __init__(self, channel_id=None):
        self.id = str(uuid.uuid1())
        self.channel_id = channel_id

    def __repr__(self):
        return '<ChannelType %r>' % self.id


class Property(TimestampMixin, db.Model):
    """
    represents the types of properties
    """
    __tablename__ = 'property'
    __table_args__ = (
        db.UniqueConstraint(
            'type',
            'key',
            'client_id',
            name='property_type_key_client_id_uc'
        ),
    )
    id = db.Column(UUID, primary_key=True)
    client_id = db.Column(UUID, db.ForeignKey(Client.id), nullable=False)
    client = db.relationship('Client', backref='properties', lazy='joined')
    key = db.Column(db.Text, nullable=False)
    type = db.Column(db.Text, nullable=False)
    disruptions = db.relationship(
        'AssociateDisruptionProperty',
        lazy='dynamic',
        back_populates='property',
        cascade='delete'
    )

    def __init__(self):
        self.id = str(uuid.uuid1())

    def __repr__(self):
        return '<%s: %s %s %s>' % (
            self.__class__.__name__, self.id, self.type, self.key
        )

    @classmethod
    def prepare_request(cls, client_id, key=None, type=None, id=None):
        request = {'client_id': client_id}
        if id:
            request['id'] = id
        if key:
            request['key'] = key
        if type:
            request['type'] = type

        return request

    @classmethod
    def all(cls, client_id, key=None, type=None):
        kargs = cls.prepare_request(client_id, key, type)

        return cls.query.filter_by(**kargs).all()

    @classmethod
    def get(cls, client_id, id=None, key=None, type=None):
        kargs = cls.prepare_request(client_id, key, type, id)

        return cls.query.filter_by(**kargs).first()
